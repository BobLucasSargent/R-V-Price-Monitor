"""
R&V IPC — Frávega collector (Playwright).

Frávega is a VTEX-based SPA. Covers:
- COICOP 05 Equipamiento hogar (~7.1%)
- COICOP 09 Recreación y cultura (~8.4%)
"""
from collectors.base import PlaywrightCollector, PriceObservation, parse_price_ar
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

SEARCH_TERMS = {
    "05.3": [
        "heladera", "lavarropas", "microondas",
        "aire acondicionado", "horno electrico",
    ],
    "09.1": [
        "smart tv 50", "notebook", "celular samsung",
        "celular motorola", "tablet",
    ],
}


@register_collector
class FravegaCollector(PlaywrightCollector):
    collector_id = "fravega"
    division_coicop = "05"
    description = "Frávega — Electrodomésticos y electrónica (Playwright)"

    def collect_with_page(self, page) -> list[PriceObservation]:
        observations = []

        for coicop_code, terms in SEARCH_TERMS.items():
            division = coicop_code.split(".")[0]

            for term in terms:
                try:
                    url = f"https://www.fravega.com/l/?keyword={term}"
                    page.goto(url, wait_until="networkidle", timeout=20000)
                    page.wait_for_timeout(3000)

                    # Frávega product cards
                    cards = page.query_selector_all(
                        "[class*='ProductCard'], "
                        "article[class*='product'], "
                        "[data-testid*='product'], "
                        "[class*='sc-']"  # Styled components fallback
                    )

                    if not cards:
                        # Try more generic approach
                        cards = page.query_selector_all("a[href*='/p/']")

                    for card in cards[:4]:
                        try:
                            name_el = card.query_selector(
                                "[class*='ProductName'], [class*='product-name'], "
                                "[class*='title'], h3, h4, span[class*='name']"
                            )
                            price_el = card.query_selector(
                                "[class*='Price'], [class*='price'], "
                                "[class*='selling'], [data-testid*='price']"
                            )

                            if not name_el or not price_el:
                                continue

                            name = name_el.inner_text().strip()
                            price = parse_price_ar(price_el.inner_text().strip())

                            if price and price > 0 and len(name) > 3:
                                observations.append(PriceObservation(
                                    producto=name,
                                    precio=price,
                                    categoria_coicop=coicop_code,
                                    division_coicop=division,
                                    fuente="Frávega",
                                    url=url,
                                    metadata={"term": term},
                                ))
                        except Exception:
                            continue

                except Exception as e:
                    log.debug("fravega.search_error", term=term, error=str(e))

        return observations
