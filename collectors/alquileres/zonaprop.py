"""
R&V IPC — Alquileres collector (Playwright + API fallback).

Covers COICOP 04 Vivienda y servicios (~11.8%).
Primary: ZonaProp (Playwright for anti-bot protection)
Fallback: Argenprop or Mercado Libre Inmuebles API
"""
from collectors.base import PlaywrightCollector, PriceObservation, parse_price_ar
from collectors.registry import register_collector
import structlog
import re

log = structlog.get_logger()

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
]


@register_collector
class AlquileresCollector(PlaywrightCollector):
    collector_id = "alquileres"
    division_coicop = "04"
    description = "Alquileres — ZonaProp (Playwright)"

    def collect_with_page(self, page) -> list[PriceObservation]:
        observations = []

        for profile in SEARCH_PROFILES:
            try:
                page.goto(profile["url"], wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(4000)

                prices = self._extract_ars_rents(page)

                if prices:
                    median = sorted(prices)[len(prices) // 2]
                    observations.append(PriceObservation(
                        producto=f"Alquiler {profile['desc']}",
                        precio=median,
                        unidad="ARS/mes",
                        categoria_coicop="04.1.1",
                        division_coicop="04",
                        fuente="ZonaProp",
                        url=profile["url"],
                        metadata={
                            "n_listings": len(prices),
                            "profile": profile["desc"],
                            "min": min(prices),
                            "max": max(prices),
                        },
                    ))
            except Exception as e:
                log.debug("alquileres.zonaprop_error",
                          profile=profile["desc"], error=str(e))

        return observations

    def _extract_ars_rents(self, page) -> list[float]:
        """Extract ARS rental prices from ZonaProp listings."""
        prices = []

        # ZonaProp uses data-qa attributes and various class patterns
        price_elements = page.query_selector_all(
            "[data-qa='POSTING_CARD_PRICE'], "
            "[class*='postingPrice'], "
            "[class*='price-tag'], "
            "[class*='Price']"
        )

        for el in price_elements[:25]:
            try:
                text = el.inner_text().strip()

                # Skip USD prices
                if "USD" in text.upper() or "U$S" in text.upper() or "U$" in text.upper():
                    continue

                price = parse_price_ar(text)
                # Sanity: monthly rent in GBA 2025-2026
                if price and 100_000 < price < 5_000_000:
                    prices.append(price)
            except Exception:
                continue

        return prices
