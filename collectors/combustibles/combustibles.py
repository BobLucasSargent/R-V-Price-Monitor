"""
Combustibles collector — surtidores.com.ar (YPF CABA, auto-updating)
=====================================================================
Scrapes YPF CABA prices from surtidores.com.ar/precios/ which has a
clean HTML table updated whenever YPF changes prices.

Only YPF (auto-updating). Shell/Axion excluded because no scrapeable
source found — they follow YPF anyway (55% market share sets the pace).

Division COICOP: 07 (Transporte)
Category: 07.2.2 (Combustibles y lubricantes)

Fuel prices have 3.8% weight in the IPC (source: INDEC).
"""

import re
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

SURTIDORES_URL = "https://surtidores.com.ar/precios/"

# Fallback prices — only used if scraping fails completely
# Last updated: 2026-04-07 (source: surtidores.com.ar + Infobae)
# YPF froze prices for 45 days from April 1, 2026
FALLBACK_PRICES = {
    "Nafta Súper YPF (por litro)": 1999.0,
    "Nafta Infinia YPF (por litro)": 2207.0,
    "Gasoil Diesel 500 YPF (por litro)": 2065.0,
    "Gasoil Infinia Diesel YPF (por litro)": 2271.0,
}

# Map table row labels to product names
FUEL_NAMES = {
    "Super": "Nafta Súper YPF (por litro)",
    "Premium": "Nafta Infinia YPF (por litro)",
    "Gasoil": "Gasoil Diesel 500 YPF (por litro)",
    "Euro": "Gasoil Infinia Diesel YPF (por litro)",
}


@register_collector
class CombustiblesCollector(BaseCollector):
    """Collect YPF fuel prices from surtidores.com.ar (auto-updating)."""

    collector_id = "combustibles"
    division_coicop = "07"
    description = "Combustibles — YPF CABA (surtidores.com.ar)"

    def collect(self) -> list[PriceObservation]:
        # Try scraping surtidores.com.ar first
        scraped = self._scrape_surtidores()

        if scraped:
            log.info("combustibles.surtidores_ok", count=len(scraped))
            return scraped

        # Fallback to hardcoded YPF prices
        log.warning("combustibles.surtidores_failed_using_fallback")
        return [
            PriceObservation(
                producto=name,
                precio=price,
                unidad="litro",
                categoria_coicop="07.2.2",
                division_coicop="07",
                fuente="combustibles_referencia",
            )
            for name, price in FALLBACK_PRICES.items()
        ]

    def _scrape_surtidores(self) -> list[PriceObservation] | None:
        """
        Scrape surtidores.com.ar/precios/ for latest YPF CABA prices.

        Page has HTML tables per year. The 2026 table looks like:
        | 2026    | Enero | Febrero | Marzo | Abril | ... |
        | Super   | 1566  | 1609    | 1999  | 1999  |     |
        | Premium | 1780  | 1845    | 2207  | 2207  |     |
        | Gasoil  | 1601  | 1658    | 2065  | 2065  |     |
        | Euro    | 1809  | 1861    | 2271  | 2271  |     |

        We grab the rightmost non-empty value in each row.
        """
        try:
            resp = self.fetch(SURTIDORES_URL)
            html = resp.text

            # Find the 2026 section
            parts = html.split("2026")
            if len(parts) < 2:
                log.warning("combustibles.no_2026_section")
                return None

            # Take content after first "2026", stop before "2025"
            section = parts[1]
            if "2025" in section:
                section = section.split("2025")[0]

            prices: dict[str, float] = {}

            for fuel_key, fuel_name in FUEL_NAMES.items():
                # Find the row for this fuel type
                pattern = rf'(?:<td[^>]*>\s*<strong>)?{fuel_key}(?:</strong>\s*</td>)?.*?</tr>'
                match = re.search(pattern, section, re.DOTALL | re.IGNORECASE)
                if not match:
                    # Try simpler pattern
                    pattern2 = rf'{fuel_key}.*?</tr>'
                    match = re.search(pattern2, section, re.DOTALL | re.IGNORECASE)
                if not match:
                    continue

                row_html = match.group(0)

                # Extract all numbers from <td> tags in this row
                numbers = re.findall(r'<td[^>]*>\s*(\d[\d.]*)\s*</td>', row_html)
                if not numbers:
                    continue

                # Take the last (most recent month) value
                for num_str in reversed(numbers):
                    try:
                        # Handle thousands separator: "1.999" vs decimal "1999"
                        if "." in num_str and len(num_str.split(".")[-1]) == 3:
                            val = float(num_str.replace(".", ""))
                        else:
                            val = float(num_str)

                        if val > 100:  # Sanity: fuel must be > $100/liter
                            prices[fuel_name] = val
                            break
                    except ValueError:
                        continue

            if len(prices) < 3:
                log.warning("combustibles.insufficient_prices", found=len(prices))
                return None

            return [
                PriceObservation(
                    producto=name,
                    precio=price,
                    unidad="litro",
                    categoria_coicop="07.2.2",
                    division_coicop="07",
                    fuente="surtidores.com.ar",
                    url=SURTIDORES_URL,
                )
                for name, price in prices.items()
            ]

        except Exception as e:
            log.warning("combustibles.scrape_error", error=str(e))
            return None
