"""
R&V IPC — Comunicaciones collector.

Covers COICOP 08 Comunicación (2.81% peso GBA):
- 08.3.2 Telefonía móvil (1.39%)
- 08.3.3 Internet (0.76%)
- 08.3.1 Telefonía fija (0.58%)

Scrapes plan prices from Personal, Claro, Movistar, Flow, Telecentro.
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
from bs4 import BeautifulSoup
import structlog
import re

log = structlog.get_logger()

# Target pages for plan prices
SOURCES = [
    # Mobile plans
    {
        "nombre": "Personal plan celular",
        "url": "https://www.personal.com.ar/planes",
        "coicop": "08.3.2",
        "tipo": "celular",
    },
    {
        "nombre": "Claro plan celular",
        "url": "https://www.claro.com.ar/personas/planes-702",
        "coicop": "08.3.2",
        "tipo": "celular",
    },
    {
        "nombre": "Movistar plan celular",
        "url": "https://www.movistar.com.ar/planes",
        "coicop": "08.3.2",
        "tipo": "celular",
    },
    # Internet / cable
    {
        "nombre": "Flow internet + cable",
        "url": "https://www.flow.com.ar/packs",
        "coicop": "08.3.3",
        "tipo": "internet",
    },
    {
        "nombre": "Telecentro internet",
        "url": "https://telecentro.com.ar/internet",
        "coicop": "08.3.3",
        "tipo": "internet",
    },
]


@register_collector
class ComunicacionesCollector(BaseCollector):
    collector_id = "comunicaciones"
    division_coicop = "08"
    description = "Comunicaciones — Planes celular e internet"

    def collect(self) -> list[PriceObservation]:
        observations = []

        for source in SOURCES:
            try:
                prices = self._scrape_plans(source["url"])
                if prices:
                    # Take median plan price
                    median = sorted(prices)[len(prices) // 2]
                    observations.append(PriceObservation(
                        producto=source["nombre"],
                        precio=median,
                        unidad="ARS/mes",
                        categoria_coicop=source["coicop"],
                        division_coicop="08",
                        fuente=source["nombre"].split(" ")[0],
                        url=source["url"],
                        metadata={
                            "tipo": source["tipo"],
                            "n_planes": len(prices),
                            "min": min(prices),
                            "max": max(prices),
                        },
                    ))
            except Exception as e:
                log.warning("comunicaciones.source_error",
                            source=source["nombre"], error=str(e))

        return observations

    def _scrape_plans(self, url: str) -> list[float]:
        """Extract plan prices from a telecom provider page."""
        prices = []

        try:
            resp = self.fetch(url)
            soup = BeautifulSoup(resp.text, "lxml")

            # Generic price selectors that work across telecom sites
            price_elements = soup.select(
                "[class*='price'], [class*='Price'], "
                "[class*='valor'], [class*='Valor'], "
                "[class*='monto'], [data-price], "
                ".plan-price, .pack-price"
            )

            for el in price_elements[:15]:
                text = el.get_text(strip=True)
                price = self._parse_price(text)
                # Sanity: monthly telecom plans in AR (2025-2026)
                if price and 5_000 < price < 200_000:
                    prices.append(price)

        except Exception as e:
            log.debug("comunicaciones.scrape_error", url=url, error=str(e))

        return prices

    @staticmethod
    def _parse_price(text: str) -> float | None:
        text = text.replace("$", "").replace(".", "").replace(",", ".").strip()
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(match.group(1)) if match else None
