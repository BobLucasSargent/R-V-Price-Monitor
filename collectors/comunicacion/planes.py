"""
R&V IPC — Comunicaciones collector (Playwright).

Covers COICOP 08 Comunicación (~3.2%).
Telecom sites (Personal, Claro, Movistar, Flow, Telecentro) are all SPAs.
"""
from collectors.base import PlaywrightCollector, PriceObservation, parse_price_ar
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

SOURCES = [
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
    {
        "nombre": "Telecentro internet",
        "url": "https://telecentro.com.ar/internet",
        "coicop": "08.3.3",
        "tipo": "internet",
    },
]


@register_collector
class ComunicacionesCollector(PlaywrightCollector):
    collector_id = "comunicaciones"
    division_coicop = "08"
    description = "Comunicaciones — Planes celular e internet (Playwright)"

    def collect_with_page(self, page) -> list[PriceObservation]:
        observations = []

        for source in SOURCES:
            try:
                page.goto(source["url"], wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(4000)

                prices = self._extract_plan_prices(page)

                if prices:
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
                log.debug("comunicaciones.source_error",
                          source=source["nombre"], error=str(e))

        return observations

    def _extract_plan_prices(self, page) -> list[float]:
        """Extract plan prices from telecom provider page."""
        prices = []

        # Generic price selectors across telecom sites
        price_elements = page.query_selector_all(
            "[class*='price'], [class*='Price'], "
            "[class*='valor'], [class*='Valor'], "
            "[class*='monto'], [data-price], "
            "[class*='plan-price'], [class*='pack-price'], "
            "[class*='amount'], [class*='Amount']"
        )

        for el in price_elements[:20]:
            try:
                text = el.inner_text().strip()
                price = parse_price_ar(text)
                # Monthly telecom plan in AR 2025-2026
                if price and 5_000 < price < 200_000:
                    prices.append(price)
            except Exception:
                continue

        return prices
