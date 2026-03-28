"""
R&V IPC — Coto Digital collector.

Scrapes cotodigital3.com.ar for grocery prices.
Coto is a major supermarket chain in GBA.
HTML scraping — less stable than VTEX APIs but covers different products.
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
from bs4 import BeautifulSoup
import structlog
import re

log = structlog.get_logger()

COTO_SEARCH = "https://www.cotodigital3.com.ar/sitios/cdigi/browse"

# Canasta representative products by COICOP
SEARCH_TERMS = {
    "01.1.1": ["pan lactal", "arroz", "harina 000", "fideos"],
    "01.1.2": ["carne picada", "pollo entero", "milanesa"],
    "01.1.4": ["leche entera", "yogur", "queso cremoso", "huevos"],
    "01.1.5": ["aceite girasol"],
    "01.1.7": ["tomate redondo", "papa", "cebolla"],
    "01.1.8": ["azúcar", "dulce de leche"],
    "01.2.1": ["yerba mate", "café instantáneo"],
    "01.2.2": ["coca cola 2.25", "agua mineral"],
    "05.6.1": ["detergente", "lavandina", "papel higiénico"],
    "12.1.3": ["shampoo", "desodorante", "jabón tocador"],
}


@register_collector
class CotoCollector(BaseCollector):
    collector_id = "coto"
    division_coicop = "01"
    description = "Coto Digital — Supermercado GBA"

    def collect(self) -> list[PriceObservation]:
        observations = []

        for coicop_code, terms in SEARCH_TERMS.items():
            division = coicop_code.split(".")[0]

            for term in terms:
                try:
                    products = self._search(term)
                    for p in products[:3]:  # Top 3 per term
                        observations.append(PriceObservation(
                            producto=p["name"],
                            precio=p["price"],
                            categoria_coicop=coicop_code,
                            division_coicop=division,
                            fuente="Coto Digital",
                            url=p.get("url", ""),
                        ))
                except Exception as e:
                    log.warning("coto.term_error", term=term, error=str(e))

        return observations

    def _search(self, term: str) -> list[dict]:
        """Search Coto Digital and parse product cards."""
        products = []

        resp = self.fetch(
            COTO_SEARCH,
            params={"_dyncharset": "utf-8", "Dy": "1", "Ntt": term, "Nty": "1"},
        )

        soup = BeautifulSoup(resp.text, "lxml")

        # Coto uses a product list with specific classes
        cards = soup.select(
            ".product-item, .product_info_container, "
            "[class*='product'], .atg_store_productContainer"
        )

        for card in cards[:5]:
            try:
                # Product name
                name_el = card.select_one(
                    ".product-name, .product_info_producto, "
                    "[class*='productName'], .descrip_full"
                )
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)

                # Price — Coto shows price in various formats
                price_el = card.select_one(
                    ".price, .atg_store_productPrice, "
                    "[class*='price'], .precio_unitario"
                )
                if not price_el:
                    continue

                price = self._parse_price(price_el.get_text(strip=True))
                if price and price > 0:
                    link = card.select_one("a")
                    url = ""
                    if link and link.get("href"):
                        href = link["href"]
                        if not href.startswith("http"):
                            url = f"https://www.cotodigital3.com.ar{href}"
                        else:
                            url = href

                    products.append({"name": name, "price": price, "url": url})

            except Exception as e:
                log.debug("coto.card_parse_error", error=str(e))

        return products

    @staticmethod
    def _parse_price(text: str) -> float | None:
        text = text.replace("$", "").replace(".", "").replace(",", ".").strip()
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(match.group(1)) if match else None
