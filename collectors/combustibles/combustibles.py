"""
Combustibles collector — surtidores.com.ar + fallback hardcoded
================================================================
Scrapes YPF CABA prices from surtidores.com.ar/precios/ which has a
clean HTML table with monthly prices per fuel type.
 
Fuel prices in Argentina change every few weeks (not daily), so this
collector also has hardcoded fallback values that should be updated
when YPF announces price changes.
 
Division COICOP: 07 (Transporte)
Category: 07.2.2 (Combustibles y lubricantes)
 
Current prices (April 2026, YPF CABA — frozen for 45 days):
  Nafta Súper:    $1.999/litro
  Infinia:        $2.207/litro
  Diesel 500:     $2.065/litro
  Infinia Diesel: $2.271/litro
"""
 
import re
from collectors.base import BaseCollector, PriceObservation, parse_price_ar
import structlog
 
log = structlog.get_logger()
 
SURTIDORES_URL = "https://surtidores.com.ar/precios/"
 
# Fallback prices — update these when YPF changes prices
# Last updated: 2026-04-07 (source: surtidores.com.ar, Infobae)
FALLBACK_PRICES = {
    "Nafta Súper YPF (por litro)": 1999.0,
    "Nafta Premium Infinia YPF (por litro)": 2207.0,
    "Gasoil Diesel 500 YPF (por litro)": 2065.0,
    "Gasoil Infinia Diesel YPF (por litro)": 2271.0,
}
 
# Shell CABA prices (April 2026, source: Infobae 30-mar-2026)
# Shell also froze prices along with YPF for 45 days from April 1
SHELL_PRICES = {
    "Nafta Súper Shell (por litro)": 2099.0,
    "Nafta V-Power Shell (por litro)": 2379.0,
    "Gasoil Diesel Shell (por litro)": 2200.0,
    "Gasoil V-Power Diesel Shell (por litro)": 2440.0,
}
 
# Axion CABA prices (April 2026, source: Infobae 30-mar-2026)
AXION_PRICES = {
    "Nafta Súper Axion (por litro)": 2039.0,
    "Nafta Quantium Axion (por litro)": 2310.0,
    "Gasoil Diesel Axion (por litro)": 2160.0,
    "Gasoil Quantium Diesel Axion (por litro)": 2390.0,
}
 
 
class CombustiblesCollector(BaseCollector):
    """Collect fuel prices from surtidores.com.ar (YPF CABA) + hardcoded Shell."""
 
    collector_id = "combustibles"
    division_coicop = "07"
    description = "Combustibles — YPF y Shell CABA"
 
    def collect(self) -> list[PriceObservation]:
        observations: list[PriceObservation] = []
 
        # 1. Try scraping surtidores.com.ar for YPF CABA latest prices
        ypf_prices = self._scrape_surtidores()
 
        if ypf_prices:
            for name, price in ypf_prices.items():
                observations.append(PriceObservation(
                    producto=name,
                    precio=price,
                    unidad="litro",
                    categoria_coicop="07.2.2",
                    division_coicop="07",
                    fuente="surtidores.com.ar",
                    url=SURTIDORES_URL,
                ))
            log.info("combustibles.surtidores_ok", count=len(ypf_prices))
        else:
            # Fallback to hardcoded YPF prices
            log.warning("combustibles.surtidores_failed, using fallback")
            for name, price in FALLBACK_PRICES.items():
                observations.append(PriceObservation(
                    producto=name,
                    precio=price,
                    unidad="litro",
                    categoria_coicop="07.2.2",
                    division_coicop="07",
                    fuente="combustibles_referencia",
                    url="",
                ))
 
        # 2. Add Shell hardcoded prices (surtidores only has YPF)
        for name, price in SHELL_PRICES.items():
            observations.append(PriceObservation(
                producto=name,
                precio=price,
                unidad="litro",
                categoria_coicop="07.2.2",
                division_coicop="07",
                fuente="combustibles_referencia",
                url="",
            ))
 
        # 3. Add Axion hardcoded prices
        for name, price in AXION_PRICES.items():
            observations.append(PriceObservation(
                producto=name,
                precio=price,
                unidad="litro",
                categoria_coicop="07.2.2",
                division_coicop="07",
                fuente="combustibles_referencia",
                url="",
            ))
 
        return observations
 
    def _scrape_surtidores(self) -> dict[str, float] | None:
        """
        Scrape surtidores.com.ar/precios/ for the latest YPF CABA prices.
 
        The page has HTML tables with this structure (one per year):
        | 2026  | Enero | Febrero | Marzo | Abril | ... |
        | Super | 1566  | 1609    | 1999  | 1999  | ... |
        | Premium | ...                                   |
        | Gasoil  | ...                                   |
        | Euro    | ...                                   |
 
        We want the rightmost non-empty value in each row of the 2026 table.
        """
        try:
            resp = self.fetch(SURTIDORES_URL)
            html = resp.text
 
            # Find the 2026 table rows
            # The table has rows like: <td>Super</td><td>1566</td><td>1609</td>...
            # We look for the pattern after "2026"
 
            prices = {}
 
            # Extract all numbers from the 2026 section
            # Strategy: find "2026" then parse the next 4 data rows
            fuel_names = {
                "Super": "Nafta Súper YPF (por litro)",
                "Premium": "Nafta Premium Infinia YPF (por litro)",
                "Gasoil": "Gasoil Diesel 500 YPF (por litro)",
                "Euro": "Gasoil Infinia Diesel YPF (por litro)",
            }
 
            # Use regex to find table cells after 2026 marker
            # Pattern: find rows containing Super/Premium/Gasoil/Euro
            # that come after a cell containing "2026"
            section_2026 = html.split("2026")
            if len(section_2026) < 2:
                log.warning("combustibles.no_2026_section")
                return None
 
            # Take the section after first "2026" occurrence
            section = section_2026[1]
            # Only look until the next year table (2025)
            if "2025" in section:
                section = section.split("2025")[0]
 
            for fuel_key, fuel_name in fuel_names.items():
                # Find the row for this fuel type
                # Look for the fuel name followed by numbers in td tags
                pattern = rf'{fuel_key}.*?</tr>'
                match = re.search(pattern, section, re.DOTALL | re.IGNORECASE)
                if not match:
                    continue
 
                row_html = match.group(0)
 
                # Extract all numbers from td tags in this row
                numbers = re.findall(r'<td[^>]*>\s*(\d[\d.]*)\s*</td>', row_html)
                if not numbers:
                    continue
 
                # Take the last (most recent month) non-empty value
                last_price = None
                for num_str in reversed(numbers):
                    try:
                        val = float(num_str.replace(".", "")) if "." in num_str and len(num_str.split(".")[-1]) == 3 else float(num_str)
                        if val > 100:  # Sanity: fuel > $100/liter
                            last_price = val
                            break
                    except ValueError:
                        continue
 
                if last_price:
                    prices[fuel_name] = last_price
 
            if len(prices) >= 3:  # Need at least 3 of 4 fuel types
                return prices
 
            log.warning("combustibles.insufficient_prices", found=len(prices))
            return None
 
        except Exception as e:
            log.warning("combustibles.scrape_error", error=str(e))
            return None
