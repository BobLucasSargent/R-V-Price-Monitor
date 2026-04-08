"""
Comunicaciones collector — Planes celular e internet (referencia)
=================================================================
Telecom prices in Argentina change every 1-3 months (regulated).
We track reference plan prices from the 3 major carriers.

Source: celulares.com (comparator) + carrier websites
Last updated: 2026-04-08

Division COICOP: 08 (Comunicación)
Categories: 08.3.0 (Servicios de telefonía e internet)

Update procedure: when carriers announce price changes,
update the PLANES dict below. Prices are monthly subscription fees.
"""

from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

# Reference plans — cuota mensual en ARS
# Sources: celulares.com, personal.com.ar, claro.com.ar, movistar.com.ar
# Last updated: 2026-04-08
# Personal avg monthly = ~$2,984 (celulares.com feb 2026)
PLANES = {
    # Planes celular pospago
    "Personal Plan Básico 5GB (mensual)": 14500.0,
    "Personal Plan Full 20GB (mensual)": 22900.0,
    "Personal Plan Premium 50GB (mensual)": 34500.0,
    "Claro Plan Básico 5GB (mensual)": 13900.0,
    "Claro Plan Plus 20GB (mensual)": 21500.0,
    "Claro Plan Max 50GB (mensual)": 32900.0,
    "Movistar Plan Básico 5GB (mensual)": 14200.0,
    "Movistar Plan Full 20GB (mensual)": 22500.0,
    "Movistar Plan Premium 50GB (mensual)": 33900.0,
    # Internet hogar (fibra óptica)
    "Personal Flow Internet 100Mbps (mensual)": 28900.0,
    "Personal Flow Internet 300Mbps (mensual)": 38900.0,
    "Claro Internet Hogar 100Mbps (mensual)": 26500.0,
    "Movistar Fibra 100Mbps (mensual)": 27500.0,
}

SURTIDORES_TELECOM_URL = "https://ar.celulares.com/planes"


@register_collector
class ComunicacionesCollector(BaseCollector):
    """Collect telecom plan prices (cell + internet) from reference data."""

    collector_id = "comunicaciones"
    division_coicop = "08"
    description = "Comunicaciones — Planes celular e internet (referencia)"

    def collect(self) -> list[PriceObservation]:
        # Try scraping celulares.com for updated prices
        scraped = self._try_scrape_celulares()
        if scraped:
            log.info("comunicaciones.scraped_ok", count=len(scraped))
            return scraped

        # Fallback: use hardcoded reference prices
        log.info("comunicaciones.using_reference", count=len(PLANES))
        return [
            PriceObservation(
                producto=name,
                precio=price,
                unidad="mes",
                categoria_coicop="08.3.0",
                division_coicop="08",
                fuente="comunicaciones_referencia",
            )
            for name, price in PLANES.items()
        ]

    def _try_scrape_celulares(self) -> list[PriceObservation] | None:
        """
        Try to scrape celulares.com for current plan prices.
        The site renders via JS so this may not work from all environments.
        Returns None if scraping fails, falling back to hardcoded.
        """
        try:
            # celulares.com has structured data but renders client-side
            # Try fetching and parsing what we can
            resp = self.fetch(
                "https://ar.celulares.com/personal/planes/personas",
            )
            html = resp.text

            # Look for price patterns in the HTML
            # celulares.com shows prices like "$14.500/mes"
            import re
            prices_found = re.findall(
                r'\$\s*([\d.]+(?:,\d+)?)\s*/mes',
                html,
            )

            if len(prices_found) >= 5:
                observations = []
                for i, price_str in enumerate(prices_found[:10]):
                    try:
                        price = float(
                            price_str.replace(".", "").replace(",", ".")
                        )
                        if 5000 < price < 100000:
                            observations.append(PriceObservation(
                                producto=f"Plan celular Personal #{i+1} (mensual)",
                                precio=price,
                                unidad="mes",
                                categoria_coicop="08.3.0",
                                division_coicop="08",
                                fuente="celulares.com",
                                url="https://ar.celulares.com/personal/planes",
                            ))
                    except ValueError:
                        continue

                if len(observations) >= 3:
                    return observations

            return None

        except Exception as e:
            log.debug("comunicaciones.scrape_failed", error=str(e))
            return None
