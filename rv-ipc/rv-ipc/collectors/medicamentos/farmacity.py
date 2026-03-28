"""
R&V IPC — Farmacity collector.

Covers COICOP 06.1.1 Productos farmacéuticos (3.53% weight GBA).
Farmacity has a well-structured ecommerce site.
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
from bs4 import BeautifulSoup
import structlog

log = structlog.get_logger()

FARMACITY_SEARCH = "https://www.farmacity.com/buscapagina"

# Representative basket of OTC medicines and health products
CANASTA_SALUD = [
    {"term": "ibuprofeno 400", "coicop": "06.1.1"},
    {"term": "paracetamol 500", "coicop": "06.1.1"},
    {"term": "aspirina", "coicop": "06.1.1"},
    {"term": "tafirol", "coicop": "06.1.1"},
    {"term": "amoxicilina", "coicop": "06.1.1"},
    {"term": "omeprazol", "coicop": "06.1.1"},
    {"term": "alcohol en gel", "coicop": "06.1.2"},
    {"term": "curitas", "coicop": "06.1.2"},
]


@register_collector
class FarmacityCollector(BaseCollector):
    collector_id = "farmacity"
    division_coicop = "06"
    description = "Farmacity — Medicamentos y salud"

    def collect(self) -> list[PriceObservation]:
        observations = []

        for item in CANASTA_SALUD:
            try:
                resp = self.fetch(
                    "https://www.farmacity.com/busca",
                    params={"ft": item["term"]},
                )
                soup = BeautifulSoup(resp.text, "lxml")

                # Farmacity product cards
                products = soup.select(".product-card, .vtex-product-summary")

                for prod in products[:3]:
                    name_el = prod.select_one(".product-name, [class*='productName']")
                    price_el = prod.select_one(
                        ".best-price, [class*='sellingPrice'], [class*='price']"
                    )

                    if not name_el or not price_el:
                        continue

                    name = name_el.get_text(strip=True)
                    price = self._parse_price(price_el.get_text(strip=True))

                    if price and price > 0:
                        observations.append(PriceObservation(
                            producto=name,
                            precio=price,
                            categoria_coicop=item["coicop"],
                            division_coicop="06",
                            fuente="Farmacity",
                            url="https://www.farmacity.com",
                        ))

            except Exception as e:
                log.warning("farmacity.search_error", term=item["term"], error=str(e))

        return observations

    @staticmethod
    def _parse_price(text: str) -> float | None:
        import re
        text = text.replace("$", "").replace(".", "").replace(",", ".").strip()
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(match.group(1)) if match else None
