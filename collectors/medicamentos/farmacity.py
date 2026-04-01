"""
R&V IPC — Farmacity collector (Playwright).

Farmacity is a VTEX-based SPA that requires JS rendering.
Covers COICOP 06 Salud (~9.9%).
"""
from collectors.base import PlaywrightCollector, PriceObservation, parse_price_ar
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

CANASTA_SALUD = [
    {"term": "ibuprofeno 400", "coicop": "06.1.1"},
    {"term": "paracetamol 500", "coicop": "06.1.1"},
    {"term": "tafirol", "coicop": "06.1.1"},
    {"term": "omeprazol", "coicop": "06.1.1"},
    {"term": "alcohol en gel", "coicop": "06.1.2"},
    {"term": "curitas", "coicop": "06.1.2"},
    {"term": "preservativos", "coicop": "06.1.2"},
]


@register_collector
class FarmacityCollector(PlaywrightCollector):
    collector_id = "farmacity"
    division_coicop = "06"
    description = "Farmacity — Medicamentos y salud (Playwright)"

    def collect_with_page(self, page) -> list[PriceObservation]:
        observations = []

        for item in CANASTA_SALUD:
            try:
                url = f"https://www.farmacity.com/{item['term'].replace(' ', '-')}?_q={item['term']}&map=ft"
                page.goto(url, wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(3000)  # Extra wait for VTEX hydration

                # Try to find product cards — VTEX uses various selectors
                cards = page.query_selector_all(
                    "[class*='productCard'], "
                    "[class*='vtex-product-summary'], "
                    "[class*='ProductSummary'], "
                    "article[class*='product']"
                )

                if not cards:
                    # Alternative: try the search results shelf
                    cards = page.query_selector_all("[class*='galleryItem'], [class*='shelf-item']")

                for card in cards[:4]:
                    try:
                        # Name
                        name_el = card.query_selector(
                            "[class*='productName'], [class*='ProductName'], "
                            "[class*='nameContainer'] span, h3, h2"
                        )
                        if not name_el:
                            continue
                        name = name_el.inner_text().strip()

                        # Price — VTEX renders prices in spans
                        price_el = card.query_selector(
                            "[class*='sellingPrice'], [class*='price'], "
                            "[class*='Price'] span, [class*='currencyContainer']"
                        )
                        if not price_el:
                            continue

                        price_text = price_el.inner_text().strip()
                        price = parse_price_ar(price_text)

                        if price and price > 0:
                            observations.append(PriceObservation(
                                producto=name,
                                precio=price,
                                categoria_coicop=item["coicop"],
                                division_coicop="06",
                                fuente="Farmacity",
                                url=url,
                                metadata={"term": item["term"]},
                            ))
                    except Exception:
                        continue

            except Exception as e:
                log.debug("farmacity.search_error", term=item["term"], error=str(e))

        return observations
