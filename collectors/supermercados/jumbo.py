"""
R&V IPC — Jumbo (Cencosud) collector.

Uses the VTEX ecommerce API that powers jumbo.com.ar.
This is a JSON API — much more reliable than HTML scraping.

VTEX search endpoint returns structured product data with prices.
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

# VTEX API base for Jumbo Argentina
VTEX_BASE = "https://www.jumbo.com.ar/api/catalog_system/pub/products/search"

# Categories to scrape — mapped to COICOP divisions
# VTEX uses category tree IDs; we search by term instead (more resilient)
SEARCH_TERMS = {
    # 01 - Alimentos
    "01.1.1": ["pan lactal", "arroz", "fideos", "harina", "galletitas"],
    "01.1.2": ["carne picada", "pollo", "nalga", "milanesa"],
    "01.1.4": ["leche entera", "yogur", "queso cremoso", "huevos"],
    "01.1.5": ["aceite girasol", "aceite oliva"],
    "01.1.7": ["tomate", "papa", "cebolla", "lechuga"],
    "01.1.8": ["azúcar", "dulce de leche", "chocolate"],
    "01.2.1": ["yerba mate", "café"],
    "01.2.2": ["coca cola", "agua mineral", "jugo"],
    # 02 - Bebidas
    "02.1.2": ["vino tinto", "vino malbec"],
    "02.1.3": ["cerveza"],
    # 05 - Equipamiento hogar
    "05.6.1": ["detergente", "lavandina", "papel higiénico"],
    # 12 - Cuidado personal
    "12.1.3": ["shampoo", "desodorante", "jabón", "pasta dental"],
}


@register_collector
class JumboCollector(BaseCollector):
    collector_id = "jumbo"
    division_coicop = "01"  # Primary division
    description = "Jumbo (Cencosud) — VTEX API"

    def collect(self) -> list[PriceObservation]:
        observations = []

        for coicop_code, terms in SEARCH_TERMS.items():
            division = coicop_code.split(".")[0]

            for term in terms:
                try:
                    products = self._search(term)
                    for p in products[:5]:  # Top 5 per term
                        obs = self._parse_product(p, coicop_code, division)
                        if obs:
                            observations.append(obs)
                except Exception as e:
                    log.warning("jumbo.term_error", term=term, error=str(e))

        return observations

    def _search(self, term: str, limit: int = 10) -> list[dict]:
        """Search VTEX catalog."""
        resp = self.fetch_json(
            VTEX_BASE,
            params={"ft": term, "_from": 0, "_to": limit - 1},
            headers={
                **self.client.headers,
                "Accept": "application/json",
            },
        )
        return resp if isinstance(resp, list) else []

    def _parse_product(self, product: dict, coicop: str, division: str) -> PriceObservation | None:
        """Extract price from VTEX product JSON."""
        try:
            name = product.get("productName", "")
            # VTEX nests prices in items[0].sellers[0].commertialOffer
            items = product.get("items", [])
            if not items:
                return None

            seller_info = items[0].get("sellers", [{}])[0]
            offer = seller_info.get("commertialOffer", {})
            price = offer.get("Price", 0)
            list_price = offer.get("ListPrice", price)

            if price <= 0:
                return None

            # Use the actual selling price (may include promotions)
            product_url = product.get("link", "")
            if product_url and not product_url.startswith("http"):
                product_url = f"https://www.jumbo.com.ar{product_url}"

            return PriceObservation(
                producto=name,
                precio=price,
                unidad="unidad",
                categoria_coicop=coicop,
                division_coicop=division,
                fuente="Jumbo (VTEX)",
                url=product_url,
            )
        except (KeyError, IndexError, TypeError) as e:
            log.debug("jumbo.parse_error", product=product.get("productName", "?"), error=str(e))
            return None
