"""
R&V IPC — Frávega collector.

Covers:
- COICOP 05.3 Artefactos para el hogar (1.14%)
- COICOP 09.1 Equipos audiovisuales y procesamiento (1.34%)

Frávega has a VTEX-based ecommerce platform.
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
from bs4 import BeautifulSoup
import structlog
import re

log = structlog.get_logger()

# Products by COICOP
SEARCH_TERMS = {
    # 05 - Equipamiento hogar
    "05.3": [
        "heladera", "lavarropas", "microondas",
        "aire acondicionado", "horno eléctrico",
    ],
    # 09 - Recreación y cultura (audiovisual + informática)
    "09.1": [
        "smart tv 50", "notebook", "celular samsung",
        "celular motorola", "tablet",
    ],
}

FRAVEGA_SEARCH = "https://www.fravega.com/l/"


@register_collector
class FravegaCollector(BaseCollector):
    collector_id = "fravega"
    division_coicop = "05"
    description = "Frávega — Electrodomésticos y electrónica"

    def collect(self) -> list[PriceObservation]:
        observations = []

        for coicop_code, terms in SEARCH_TERMS.items():
            division = coicop_code.split(".")[0]

            for term in terms:
                try:
                    products = self._search(term)
                    for p in products[:3]:
                        observations.append(PriceObservation(
                            producto=p["name"],
                            precio=p["price"],
                            categoria_coicop=coicop_code,
                            division_coicop=division,
                            fuente="Frávega",
                            url=p.get("url", ""),
                        ))
                except Exception as e:
                    log.warning("fravega.term_error", term=term, error=str(e))

        return observations

    def _search(self, term: str) -> list[dict]:
        """Search Frávega and parse product results."""
        products = []

        try:
            # Frávega uses URL-based search
            search_slug = term.replace(" ", "-")
            resp = self.fetch(
                f"https://www.fravega.com/l/?keyword={term}",
            )

            soup = BeautifulSoup(resp.text, "lxml")

            # Frávega product cards
            cards = soup.select(
                "[class*='product-card'], [class*='ProductCard'], "
                "article[class*='product'], [data-testid*='product']"
            )

            for card in cards[:5]:
                name_el = card.select_one(
                    "[class*='product-name'], [class*='ProductName'], "
                    "[class*='title'], h3, h4"
                )
                price_el = card.select_one(
                    "[class*='price'], [class*='Price'], "
                    "[class*='selling'], [data-testid*='price']"
                )

                if not name_el or not price_el:
                    continue

                name = name_el.get_text(strip=True)
                price = self._parse_price(price_el.get_text(strip=True))

                if price and price > 0:
                    link = card.select_one("a[href]")
                    url = ""
                    if link:
                        href = link["href"]
                        url = href if href.startswith("http") else f"https://www.fravega.com{href}"

                    products.append({"name": name, "price": price, "url": url})

        except Exception as e:
            log.debug("fravega.search_error", term=term, error=str(e))

        return products

    @staticmethod
    def _parse_price(text: str) -> float | None:
        text = text.replace("$", "").replace(".", "").replace(",", ".").strip()
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(match.group(1)) if match else None
