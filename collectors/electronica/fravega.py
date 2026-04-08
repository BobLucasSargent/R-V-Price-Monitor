"""
Frávega collector — VTEX Search API (API-based, no Playwright)
===============================================================
Frávega uses VTEX (client since 2014). Public search API confirmed
working 2026-04-08.

API: GET https://www.fravega.com/api/catalog_system/pub/products/search/{path}?_from=0&_to=N

Note: Frávega is a marketplace with multiple sellers. We take the price
from the first seller with IsAvailable=true.

Covers COICOP:
- 05.3.1 Electrodomésticos grandes (heladeras, lavarropas, cocinas)
- 05.3.2 Electrodomésticos pequeños (licuadoras, cafeteras, planchas)
- 09.1.1 Equipos audiovisuales (TVs, audio)
- 09.1.3 Equipos informáticos (notebooks, tablets)
"""

from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

BASE_URL = "https://www.fravega.com"
SEARCH_PATH = "/api/catalog_system/pub/products/search"

# (category_path or search_term, division, coicop, n_items, is_fulltext)
CATEGORIES = [
    # Div 05: Equipamiento y mantenimiento del hogar
    # 05.3.1 Electrodomésticos grandes
    ("electrodomesticos/heladeras", "05", "05.3.1", 10, False),
    ("electrodomesticos/lavarropas", "05", "05.3.1", 10, False),
    ("electrodomesticos/cocinas", "05", "05.3.1", 10, False),
    # 05.3.2 Electrodomésticos pequeños
    ("electrodomesticos/microondas", "05", "05.3.2", 8, False),
    ("pequenos-electrodomesticos/licuadoras-y-minipimers", "05", "05.3.2", 8, False),
    ("pequenos-electrodomesticos/cafeteras", "05", "05.3.2", 8, False),
    # Div 09: Recreación y cultura
    # 09.1.1 Equipos audiovisuales
    ("tv-y-video/televisores", "09", "09.1.1", 10, False),
    # 09.1.3 Equipos informáticos
    ("informatica/notebooks", "09", "09.1.3", 8, False),
    ("celulares-y-tablets/celulares-y-smartphones", "09", "09.1.3", 8, False),
]


@register_collector
class FravegaCollector(BaseCollector):
    """Collect appliance and electronics prices from Frávega via VTEX API."""

    collector_id = "fravega"
    division_coicop = "05"
    description = "Frávega — Electrodomésticos y electrónica (VTEX API)"

    def collect(self) -> list[PriceObservation]:
        observations: list[PriceObservation] = []

        for cat_path, division, coicop, n_items, is_ft in CATEGORIES:
            try:
                if is_ft:
                    url = f"{BASE_URL}{SEARCH_PATH}"
                    params = {"ft": cat_path, "_from": 0, "_to": n_items - 1}
                else:
                    url = f"{BASE_URL}{SEARCH_PATH}/{cat_path}"
                    params = {"_from": 0, "_to": n_items - 1}

                products = self.fetch_json(url, params=params)

                for product in products:
                    obs = self._parse(product, division, coicop, cat_path)
                    if obs:
                        observations.append(obs)

                log.info(
                    "fravega.category",
                    category=cat_path,
                    products=len(products),
                )

            except Exception as e:
                log.warning(
                    "fravega.category_error",
                    category=cat_path,
                    error=str(e),
                )
                continue

        return observations

    @staticmethod
    def _parse(
        product: dict,
        division: str,
        coicop: str,
        cat_path: str,
    ) -> PriceObservation | None:
        """
        Parse one VTEX product JSON.

        Frávega is a marketplace: products can have multiple sellers.
        We pick the first seller with IsAvailable=true and Price > 0.
        """
        try:
            name = product.get("productName", "")
            brand = product.get("brand", "")
            link = product.get("link", "")

            items = product.get("items", [])
            if not items:
                return None

            # Find the best available seller across all items
            price = 0
            seller_name = ""

            for item in items:
                sellers = item.get("sellers", [])
                for seller in sellers:
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

            # Sanity: Frávega sells from ~$5k (small items) to ~$10M (commercial)
            # Skip extremes — commercial/industrial equipment and accessories
            if price < 5_000 or price > 10_000_000:
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
                    "vtex_category": cat_path,
                },
            )

        except (KeyError, IndexError, TypeError):
            return None
