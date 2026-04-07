"""
Farmacity collector — VTEX Search API (API-based, no Playwright needed)
======================================================================
Farmacity runs on VTEX. Their public search API returns structured JSON
with product name, price, brand, SKU, and availability.
 
API endpoint (confirmed working 2026-04-07):
  GET https://www.farmacity.com/api/catalog_system/pub/products/search/{category_path}?_from=0&_to=N
 
Price path in JSON:
  product["items"][0]["sellers"][0]["commertialOffer"]["Price"]
 
This collector runs via httpx (no browser needed) → can run in Railway
directly, NOT in GH Actions.
"""
 
import httpx
import logging
from collectors.base import register_collector
 
logger = logging.getLogger(__name__)
 
COLLECTOR_ID = "farmacity"
BASE_URL = "https://www.farmacity.com"
SEARCH_API = "/api/catalog_system/pub/products/search"
 
# ── Categories to scrape ─────────────────────────────────────────────
# Each tuple: (category_path, division_ipc, items_to_fetch)
# VTEX max per request = 50, we fetch 20 per category to keep it fast
CATEGORIES = [
    # División 06: Salud (medicamentos OTC)
    ("medicamentos-venta-libre/analgesicos", "06", 20),
    ("medicamentos-venta-libre/digestivos", "06", 15),
    ("medicamentos-venta-libre/gripe-y-resfrio", "06", 15),
    # División 12: Bienes y servicios diversos (cuidado personal)
    ("belleza/cuidado-facial/cremas-faciales", "12", 10),
    ("belleza/cuidado-corporal/cremas-corporales", "12", 10),
    ("higiene-personal/higiene-bucal/cepillos-de-dientes", "12", 10),
    ("higiene-personal/desodorantes", "12", 10),
    ("higiene-personal/shampoo", "12", 10),
]
 
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
 
 
@register_collector(COLLECTOR_ID)
async def collect() -> list[dict]:
    """
    Collect prices from Farmacity via VTEX public search API.
    Returns list of dicts with keys: producto, precio, division, fuente, categoria, marca
    """
    all_prices = []
 
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers=HEADERS,
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        for cat_path, division, count in CATEGORIES:
            try:
                url = f"{SEARCH_API}/{cat_path}"
                params = {"_from": 0, "_to": count - 1}
                resp = await client.get(url, params=params)
 
                if resp.status_code != 200:
                    logger.warning(
                        f"farmacity/{cat_path}: HTTP {resp.status_code}"
                    )
                    continue
 
                products = resp.json()
                cat_prices = []
 
                for product in products:
                    record = _parse_product(product, division, cat_path)
                    if record:
                        cat_prices.append(record)
 
                all_prices.extend(cat_prices)
                logger.info(
                    f"farmacity/{cat_path}: {len(cat_prices)} precios"
                )
 
            except Exception as e:
                logger.warning(f"farmacity/{cat_path} error: {e}")
                continue
 
    logger.info(f"farmacity total: {len(all_prices)} precios")
    return all_prices
 
 
def _parse_product(product: dict, division: str, cat_path: str) -> dict | None:
    """
    Parse one VTEX product JSON into a price record.
 
    Confirmed structure (2026-04-07):
      product["productName"]  → "Ibupirac Ibuprofeno 400 mg x 12 Cáps"
      product["brand"]        → "Ibupirac"
      product["items"][0]["itemId"]  → "156090"
      product["items"][0]["sellers"][0]["commertialOffer"]["Price"]  → 3877.0
      product["items"][0]["sellers"][0]["commertialOffer"]["IsAvailable"]  → True
      product["items"][0]["sellers"][0]["commertialOffer"]["AvailableQuantity"]  → 99999
    """
    try:
        name = product.get("productName", "")
        brand = product.get("brand", "")
 
        items = product.get("items", [])
        if not items:
            return None
 
        first_item = items[0]
        sku_id = first_item.get("itemId", "")
 
        sellers = first_item.get("sellers", [])
        if not sellers:
            return None
 
        offer = sellers[0].get("commertialOffer", {})
 
        # Use "Price" (actual selling price, includes promos)
        # NOT "ListPrice" (can be higher, pre-discount price)
        price = offer.get("Price", 0)
        available = offer.get("AvailableQuantity", 0)
        is_available = offer.get("IsAvailable", False)
 
        # Skip unavailable or zero-price
        if not price or price <= 0:
            return None
        if not is_available or available <= 0:
            return None
 
        # Sanity check: skip extreme prices
        # Farmacity prices range ~$1,000 - $200,000 ARS for OTC/personal care
        if price < 500 or price > 300_000:
            logger.debug(f"farmacity skip out-of-range: {name} = ${price}")
            return None
 
        return {
            "producto": name,
            "precio": float(price),
            "division": division,
            "fuente": "farmacity",
            "categoria": cat_path,
            "marca": brand,
        }
 
    except (KeyError, IndexError, TypeError) as e:
        logger.debug(f"farmacity parse error: {e}")
        return None
