"""
Frávega collector — VTEX Search API (fulltext search)
======================================================
Frávega uses VTEX. Category paths don't match standard patterns,
so we use fulltext search (?ft=term) which is confirmed working.

API: GET https://www.fravega.com/api/catalog_system/pub/products/search?ft={term}&_from=0&_to=N

Covers COICOP:
- 05.3.1 Electrodomésticos grandes (heladeras, lavarropas, cocinas)
- 05.3.2 Electrodomésticos pequeños (microondas, cafeteras, licuadoras)
- 09.1.1 Equipos audiovisuales (TVs)
- 09.1.3 Equipos informáticos (notebooks, celulares)
"""

from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

BASE_URL = "https://www.fravega.com"
SEARCH_PATH = "/api/catalog_system/pub/products/search"

# (search_term, division, coicop, n_items)
SEARCHES = [
    # Div 05: Equipamiento del hogar — electrodomésticos grandes
    ("heladera", "05", "05.3.1", 10),
    ("lavarropas", "05", "05.3.1", 10),
    ("cocina", "05", "05.3.1", 8),
    # Div 05: Electrodomésticos pequeños
    ("microondas", "05", "05.3.2", 8),
    ("cafetera", "05", "05.3.2", 8),
    ("licuadora", "05", "05.3.2", 8),
    # Div 09: Recreación y cultura — audiovisual e informática
    ("televisor", "09", "09.1.1", 10),
    ("smart tv", "09", "09.1.1", 10),
    ("monitor", "09", "09.1.3", 8),
    ("notebook", "09", "09.1.3", 10),
    ("tablet", "09", "09.1.3", 8),
    ("celular", "09", "09.1.3", 10),
    ("auriculares", "09", "09.1.1", 8),
]

# Sanity bounds por división
PRICE_BOUNDS = {
    "05": (5_000, 10_000_000),   # electrodomésticos
    "09": (50_000, 5_000_000),   # electrónica — filtro más estricto
}
PRICE_DEFAULT = (5_000, 10_000_000)


@register_collector
class FravegaCollector(BaseCollector):
    """Collect appliance and electronics prices from Frávega via VTEX API."""

    collector_id = "fravega"
    division_coicop = "05"
    description = "Frávega — Electrodomésticos y electrónica (VTEX API)"

    def collect(self) -> list[PriceObservation]:
        observations: list[PriceObservation] = []

        for term, division, coicop, n_items in SEARCHES:
            try:
                url = f"{BASE_URL}{SEARCH_PATH}"
                params = {"ft": term, "_from": 0, "_to": n_items - 1}
                products = self.fetch_json(url, params=params)

                count = 0
                for product in products:
                    obs = self._parse(product, division, coicop, term)
                    if obs:
                        observations.append(obs)
                        count += 1

                log.info("fravega.search", term=term, found=count)

            except Exception as e:
                log.warning("fravega.search_error", term=term, error=str(e))
                continue

        return observations

    @staticmethod
    def _parse(
        product: dict,
        division: str,
        coicop: str,
        term: str,
    ) -> PriceObservation | None:
        """
        Parse one VTEX product. Frávega is a marketplace — pick the
        first seller with IsAvailable=true and Price > 0.
        """
        try:
            name = product.get("productName", "")
            brand = product.get("brand", "")
            link = product.get("link", "")

            items = product.get("items", [])
            if not items:
                return None

            price = 0
            seller_name = ""

            for item in items:
                for seller in item.get("sellers", []):
                    offer = seller.get("commertialOffer", {})
                    s_price = offer.get("Price", 0)
                    is_available = offer.get("IsAvailable", False)
                    available_qty = offer.get("AvailableQuantity", 0)

                    if s_price and s_price > 0 and is_available and available_qty > 0:
                        price = s_price
                        seller_name = seller.get("sellerName", "")
                        break
                if price > 0:
                    break

            if price <= 0:
                return None

            # Sanity bounds por división
            price_min, price_max = PRICE_BOUNDS.get(division, PRICE_DEFAULT)
            if price < price_min or price > price_max:
                return None

            return PriceObservation(
                producto=name,
                precio=float(price),
                unidad="unidad",
                categoria_coicop=coicop,
                division_coicop=division,
                fuente="fravega",
                url=link,
                metadata={
                    "brand": brand,
                    "seller": seller_name,
                    "search_term": term,
                },
            )

        except (KeyError, IndexError, TypeError):
            return None
