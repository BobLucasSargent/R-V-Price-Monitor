"""
R&V IPC — PedidosYa collector for restaurant/delivery prices.

Covers COICOP Division 11: Restaurantes y hoteles (10.84% weight).

Uses PedidosYa's public-facing API to get menu prices
for a representative basket of typical Argentine dishes.
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
from bs4 import BeautifulSoup
import structlog

log = structlog.get_logger()

# Representative basket of dishes — typical consumption
# These map to COICOP 11.1 "Restaurantes y comidas fuera del hogar"
CANASTA_DELIVERY = [
    {"term": "pizza muzzarella", "nombre": "Pizza muzzarella grande"},
    {"term": "empanadas", "nombre": "Docena de empanadas"},
    {"term": "milanesa napolitana", "nombre": "Milanesa napolitana con papas"},
    {"term": "hamburguesa", "nombre": "Hamburguesa completa"},
    {"term": "lomo", "nombre": "Sándwich de lomo"},
    {"term": "ravioles", "nombre": "Ravioles con salsa"},
    {"term": "asado", "nombre": "Parrillada / asado"},
    {"term": "ensalada caesar", "nombre": "Ensalada Caesar"},
]

# PedidosYa search API (public-facing)
PEYA_SEARCH = "https://www.pedidosya.com.ar/restaurantes/buenos-aires"


@register_collector
class PedidosYaCollector(BaseCollector):
    collector_id = "pedidosya"
    division_coicop = "11"
    description = "PedidosYa — Precios delivery GBA"

    def collect(self) -> list[PriceObservation]:
        observations = []

        for item in CANASTA_DELIVERY:
            try:
                prices = self._search_dish(item["term"])
                if prices:
                    # Take median of collected prices
                    median_price = sorted(prices)[len(prices) // 2]
                    observations.append(PriceObservation(
                        producto=item["nombre"],
                        precio=median_price,
                        unidad="porción/plato",
                        categoria_coicop="11.1",
                        division_coicop="11",
                        fuente="PedidosYa",
                        metadata={"term": item["term"], "n_prices": len(prices)},
                    ))
            except Exception as e:
                log.warning("pedidosya.item_error", item=item["term"], error=str(e))

        return observations

    def _search_dish(self, term: str) -> list[float]:
        """Search PedidosYa for dish prices."""
        prices = []
        try:
            # PedidosYa renders server-side; we parse the HTML
            resp = self.fetch(
                f"{PEYA_SEARCH}",
                params={"search": term},
            )

            soup = BeautifulSoup(resp.text, "lxml")

            # Look for price elements — PedidosYa uses various selectors
            # The exact selectors may need adjustment
            price_elements = soup.select("[class*='price'], [data-testid*='price']")

            for el in price_elements[:10]:
                text = el.get_text(strip=True)
                price = self._parse_price(text)
                if price and 500 < price < 50000:  # Sanity check
                    prices.append(price)

        except Exception as e:
            log.debug("pedidosya.search_error", term=term, error=str(e))

        return prices

    @staticmethod
    def _parse_price(text: str) -> float | None:
        """Parse price string like '$4.500' or '$ 4500'."""
        import re
        text = text.replace("$", "").replace(".", "").replace(",", ".").strip()
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if match:
            return float(match.group(1))
        return None
