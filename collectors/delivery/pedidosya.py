"""
R&V IPC — PedidosYa / Delivery collector (Playwright).

Covers COICOP 11 Restaurantes y hoteles (~12.2%).
PedidosYa is a React SPA that needs JS rendering.
"""
from collectors.base import PlaywrightCollector, PriceObservation, parse_price_ar
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

CANASTA_DELIVERY = [
    {"term": "pizza muzzarella", "nombre": "Pizza muzzarella grande"},
    {"term": "empanadas", "nombre": "Docena de empanadas"},
    {"term": "milanesa napolitana", "nombre": "Milanesa napolitana con papas"},
    {"term": "hamburguesa", "nombre": "Hamburguesa completa"},
    {"term": "lomo", "nombre": "Sándwich de lomo"},
    {"term": "ravioles", "nombre": "Ravioles con salsa"},
]


@register_collector
class PedidosYaCollector(PlaywrightCollector):
    collector_id = "pedidosya"
    division_coicop = "11"
    description = "PedidosYa — Precios delivery GBA (Playwright)"

    def collect_with_page(self, page) -> list[PriceObservation]:
        observations = []

        for item in CANASTA_DELIVERY:
            try:
                # PedidosYa search with location set to CABA
                url = f"https://www.pedidosya.com.ar/restaurantes/buenos-aires?search={item['term']}"
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(5000)  # PeYa loads dynamically

                # Collect prices from visible elements
                prices = self._extract_prices(page)

                if prices:
                    # Take median
                    sorted_prices = sorted(prices)
                    median = sorted_prices[len(sorted_prices) // 2]

                    observations.append(PriceObservation(
                        producto=item["nombre"],
                        precio=median,
                        unidad="porción/plato",
                        categoria_coicop="11.1",
                        division_coicop="11",
                        fuente="PedidosYa",
                        url=url,
                        metadata={
                            "term": item["term"],
                            "n_prices": len(prices),
                            "min": min(prices),
                            "max": max(prices),
                        },
                    ))

            except Exception as e:
                log.debug("pedidosya.search_error", term=item["term"], error=str(e))

        return observations

    def _extract_prices(self, page) -> list[float]:
        """Extract prices from PedidosYa search results."""
        prices = []

        # Try various selectors PeYa uses
        price_elements = page.query_selector_all(
            "[class*='price'], [class*='Price'], "
            "[data-testid*='price'], "
            "span[class*='currency'], "
            "[class*='amount']"
        )

        for el in price_elements[:20]:
            try:
                text = el.inner_text().strip()
                price = parse_price_ar(text)
                # Sanity: delivery dish in GBA 2025-2026 range
                if price and 2_000 < price < 80_000:
                    prices.append(price)
            except Exception:
                continue

        return prices
