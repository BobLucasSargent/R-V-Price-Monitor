"""
R&V IPC — Tarifas de servicios públicos (Playwright + reference data).

Covers COICOP 04.4/04.5:
- 04.5.1 Electricidad
- 04.5.2 Gas natural
- 04.4 Agua potable

Tariffs change discretely (every few months via regulatory resolution).
Strategy:
1. Try to scrape current tariff from utility/regulator websites
2. Fall back to reference tariffs (updated manually when resolutions change)

The reference values represent a typical GBA residential bill.
"""
from collectors.base import PlaywrightCollector, PriceObservation, parse_price_ar
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

# Reference tariffs for a typical GBA household (updated per resolution)
# These are monthly bill estimates for average consumption
# Last updated: March 2026 (Resolution ENRE XXX/2026, ENARGAS XXX/2026)
# TODO: Update these when new resolutions are published
TARIFAS_REFERENCIA = {
    "electricidad": {
        "nombre": "Electricidad Edenor — consumo medio residencial (350 kWh/bim)",
        "precio": 45000.0,  # ARS/mes approximate
        "coicop": "04.5.1",
        "fuente": "ENRE / Edenor",
        "url_scrape": "https://www.edenor.com.ar/tarifas",
    },
    "gas": {
        "nombre": "Gas natural Metrogas — consumo medio residencial",
        "precio": 28000.0,  # ARS/mes approximate
        "coicop": "04.5.2",
        "fuente": "ENARGAS / Metrogas",
        "url_scrape": "https://www.metrogas.com.ar/tarifas",
    },
    "agua": {
        "nombre": "Agua y saneamiento AySA",
        "precio": 12000.0,  # ARS/mes approximate
        "coicop": "04.4",
        "fuente": "AySA / ERAS",
        "url_scrape": "https://www.aysa.com.ar/usuarios/Factura-y-Consumo",
    },
}


@register_collector
class TarifasCollector(PlaywrightCollector):
    collector_id = "tarifas"
    division_coicop = "04"
    description = "Tarifas servicios públicos — Electricidad, gas, agua"

    def collect_with_page(self, page) -> list[PriceObservation]:
        observations = []

        for key, tarifa in TARIFAS_REFERENCIA.items():
            # Try to scrape current tariff
            scraped_price = self._try_scrape_tariff(page, tarifa["url_scrape"], key)

            if scraped_price:
                price = scraped_price
                fuente = f"{tarifa['fuente']} (scrapeado)"
            else:
                # Use reference value
                price = tarifa["precio"]
                fuente = f"{tarifa['fuente']} (referencia)"

            observations.append(PriceObservation(
                producto=tarifa["nombre"],
                precio=price,
                unidad="ARS/mes",
                categoria_coicop=tarifa["coicop"],
                division_coicop="04",
                fuente=fuente,
                url=tarifa["url_scrape"],
                metadata={"tipo": key, "es_referencia": scraped_price is None},
            ))

        return observations

    def _try_scrape_tariff(self, page, url: str, tipo: str) -> float | None:
        """Try to scrape actual tariff from utility website."""
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(3000)

            # Look for tariff tables or price elements
            price_elements = page.query_selector_all(
                "[class*='tarifa'], [class*='Tarifa'], "
                "[class*='precio'], [class*='Precio'], "
                "[class*='valor'], [class*='importe'], "
                "td[class*='price'], th[class*='price']"
            )

            prices = []
            for el in price_elements[:15]:
                try:
                    text = el.inner_text().strip()
                    price = parse_price_ar(text)
                    # Sanity: monthly utility bill in GBA
                    if price and 3_000 < price < 300_000:
                        prices.append(price)
                except Exception:
                    continue

            if prices:
                # Return median
                sorted_p = sorted(prices)
                return sorted_p[len(sorted_p) // 2]

        except Exception as e:
            log.debug(f"tarifas.scrape_error.{tipo}", error=str(e))

        return None
