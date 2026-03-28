"""
R&V IPC — ZonaProp collector.

Covers COICOP 04.1.1 Alquiler de la vivienda (3.48% peso GBA).

Scrapes ZonaProp listings to get median asking rent
for representative apartment types in GBA.
This gives a proxy for rent inflation (the actual IPC tracks
contract rents, not asking prices, but the trend is directional).
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
from bs4 import BeautifulSoup
import structlog
import re

log = structlog.get_logger()

# Representative apartment profiles for GBA
SEARCH_PROFILES = [
    {
        "desc": "2 amb CABA",
        "url": "https://www.zonaprop.com.ar/departamentos-alquiler-capital-federal-2-ambientes.html",
    },
    {
        "desc": "3 amb CABA",
        "url": "https://www.zonaprop.com.ar/departamentos-alquiler-capital-federal-3-ambientes.html",
    },
    {
        "desc": "2 amb GBA Norte",
        "url": "https://www.zonaprop.com.ar/departamentos-alquiler-zona-norte-2-ambientes.html",
    },
    {
        "desc": "2 amb GBA Oeste",
        "url": "https://www.zonaprop.com.ar/departamentos-alquiler-zona-oeste-2-ambientes.html",
    },
]


@register_collector
class ZonaPropCollector(BaseCollector):
    collector_id = "zonaprop"
    division_coicop = "04"
    description = "ZonaProp — Alquileres GBA"

    def collect(self) -> list[PriceObservation]:
        observations = []

        for profile in SEARCH_PROFILES:
            try:
                prices = self._scrape_listings(profile["url"])
                if prices:
                    # Take median asking rent
                    median = sorted(prices)[len(prices) // 2]
                    observations.append(PriceObservation(
                        producto=f"Alquiler {profile['desc']}",
                        precio=median,
                        unidad="ARS/mes",
                        categoria_coicop="04.1.1",
                        division_coicop="04",
                        fuente="ZonaProp",
                        url=profile["url"],
                        metadata={"n_listings": len(prices), "profile": profile["desc"]},
                    ))
            except Exception as e:
                log.warning("zonaprop.profile_error",
                            profile=profile["desc"], error=str(e))

        return observations

    def _scrape_listings(self, url: str) -> list[float]:
        """Scrape listing prices from a ZonaProp search results page."""
        prices = []

        resp = self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        # ZonaProp listing cards with prices
        price_elements = soup.select(
            "[data-qa='POSTING_CARD_PRICE'], "
            "[class*='price'], "
            ".price-tag, "
            ".postingCardPrice"
        )

        for el in price_elements[:20]:
            text = el.get_text(strip=True)

            # Filter: only ARS prices (not USD)
            if "USD" in text.upper() or "U$" in text.upper():
                continue

            price = self._parse_price(text)
            # Sanity check for monthly rent in GBA (2025-2026 range)
            if price and 100_000 < price < 3_000_000:
                prices.append(price)

        return prices

    @staticmethod
    def _parse_price(text: str) -> float | None:
        text = text.replace("$", "").replace(".", "").replace(",", ".").strip()
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(match.group(1)) if match else None
