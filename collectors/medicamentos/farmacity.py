"""
Farmacity collector — VTEX Search API
======================================
Farmacity runs on VTEX, which exposes a public product search API.
Returns structured JSON — no Playwright/browser needed.
 
API (confirmed working 2026-04-07):
  GET https://www.farmacity.com/api/catalog_system/pub/products/search/{path}?_from=0&_to=N
 
Price location:
  product["items"][0]["sellers"][0]["commertialOffer"]["Price"]
 
Extends BaseCollector (httpx-based), NOT PlaywrightCollector.
"""
 
from collectors.base import BaseCollector, PriceObservation
import structlog
 
log = structlog.get_logger()
 
# ── VTEX category paths to scrape ────────────────────────────────────
# (path, division_coicop, coicop_category, n_items)
CATEGORIES = [
    # División 06: Salud — medicamentos OTC
    ("medicamentos-venta-libre/analgesicos", "06", "06.1.1", 20),
    ("medicamentos-venta-libre/digestivos", "06", "06.1.1", 15),
    ("medicamentos-venta-libre/gripe-y-resfrio", "06", "06.1.1", 15),
    # División 12: Bienes y servicios diversos — cuidado personal
    ("belleza/cuidado-facial/cremas-faciales", "12", "12.1.3", 10),
    ("belleza/cuidado-corporal/cremas-corporales", "12", "12.1.3", 10),
    ("higiene-personal/higiene-bucal/cepillos-de-dientes", "12", "12.1.3", 10),
    ("higiene-personal/desodorantes", "12", "12.1.3", 10),
    ("higiene-personal/shampoo", "12", "12.1.3", 10),
]
 
BASE_URL = "https://www.farmacity.com"
SEARCH_PATH = "/api/catalog_system/pub/products/search"
 
 
class FarmacityCollector(BaseCollector):
    """Collect OTC drug and personal care prices from Farmacity via VTEX API."""
 
    collector_id = "farmacity"
    division_coicop = "06"
    description = "Farmacity — medicamentos OTC y cuidado personal (VTEX API)"
 
    def collect(self) -> list[PriceObservation]:
        observations: list[PriceObservation] = []
 
        for cat_path, division, coicop, n_items in CATEGORIES:
            try:
                url = f"{BASE_URL}{SEARCH_PATH}/{cat_path}"
                params = {"_from": 0, "_to": n_items - 1}
                products = self.fetch_json(url, params=params)
 
                for product in products:
                    obs = self._parse(product, division, coicop, cat_path)
                    if obs:
                        observations.append(obs)
 
                log.info(
                    "farmacity.category",
                    category=cat_path,
                    products=len(products),
                )
 
            except Exception as e:
                log.warning(
                    "farmacity.category_error",
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
        Parse one VTEX product into a PriceObservation.
 
        Confirmed JSON structure (2026-04-07):
          productName  → "Ibupirac Ibuprofeno 400 mg x 12 Cáps"
          brand        → "Ibupirac"
          items[0].sellers[0].commertialOffer.Price → 3877.0
          items[0].sellers[0].commertialOffer.IsAvailable → true
        """
        try:
            name = product.get("productName", "")
            brand = product.get("brand", "")
            link = product.get("link", "")
 
            items = product.get("items", [])
            if not items:
                return None
 
            sellers = items[0].get("sellers", [])
            if not sellers:
                return None
 
            offer = sellers[0].get("commertialOffer", {})
            price = offer.get("Price", 0)
            is_available = offer.get("IsAvailable", False)
            available_qty = offer.get("AvailableQuantity", 0)
 
            # Skip unavailable or zero-price
            if not price or price <= 0:
                return None
            if not is_available or available_qty <= 0:
                return None
 
            # Sanity: Farmacity OTC/personal care prices ~$500–$300k ARS
            if price < 500 or price > 300_000:
                return None
 
            return PriceObservation(
                producto=name,
                precio=float(price),
                unidad="unidad",
                categoria_coicop=coicop,
                division_coicop=division,
                fuente="farmacity",
                url=link,
                metadata={
                    "brand": brand,
                    "vtex_category": cat_path,
                },
            )
 
        except (KeyError, IndexError, TypeError):
            return None
 
