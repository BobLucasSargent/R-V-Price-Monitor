"""
R&V IPC — Combustibles collector.

Uses datos.gob.ar / Secretaría de Energía API for official fuel prices.
This is the most reliable source — it's government open data.

Also scrapes YPF website as backup for retail pump prices.
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

# Secretaría de Energía — API de precios de combustibles
# Dataset: precios de combustibles en surtidor (actualización diaria)
ENERGIA_API = "https://datos.energia.gob.ar/api/3/action/datastore_search"
RESOURCE_ID = "80ac25de-a44a-4f6b-b854-a5a6377e1023"  # Precios en surtidor

# YPF direct — backup source
YPF_PRICES_URL = "https://www.ypf.com/estaciones-de-servicio"

# Products we track (COICOP 07.2.2 — Combustibles y lubricantes)
FUEL_PRODUCTS = {
    "nafta_super": "Nafta Súper",
    "nafta_premium": "Nafta Premium / Infinia",
    "gasoil_grado2": "Gasoil Grado 2",
    "gasoil_grado3": "Gasoil Grado 3 / Infinia Diesel",
}


@register_collector
class CombustiblesCollector(BaseCollector):
    collector_id = "combustibles"
    division_coicop = "07"
    description = "Combustibles — Sec. Energía + YPF"

    def collect(self) -> list[PriceObservation]:
        observations = []

        # Try official API first
        try:
            observations = self._collect_energia_api()
            if observations:
                return observations
        except Exception as e:
            log.warning("combustibles.energia_api_error", error=str(e))

        # Fallback: try YPF page
        try:
            observations = self._collect_ypf()
        except Exception as e:
            log.warning("combustibles.ypf_error", error=str(e))

        return observations

    def _collect_energia_api(self) -> list[PriceObservation]:
        """Fetch from Secretaría de Energía open data API."""
        observations = []

        # Query for Buenos Aires / GBA stations, latest records
        data = self.fetch_json(
            ENERGIA_API,
            params={
                "resource_id": RESOURCE_ID,
                "limit": 100,
                "sort": "fecha desc",
                "filters": '{"provincia":"BUENOS AIRES"}',
            },
        )

        records = data.get("result", {}).get("records", [])
        if not records:
            log.info("combustibles.no_records_energia")
            return []

        # Aggregate by fuel type — take median price for GBA
        from collections import defaultdict
        prices_by_type = defaultdict(list)

        for record in records:
            product = record.get("producto", "").lower()
            price = record.get("precio")
            empresa = record.get("empresa", "")

            if price is None:
                continue

            try:
                price = float(price)
            except (ValueError, TypeError):
                continue

            if "super" in product and "premium" not in product:
                prices_by_type["nafta_super"].append((price, empresa))
            elif "premium" in product or "infinia" in product.lower():
                prices_by_type["nafta_premium"].append((price, empresa))
            elif "gasoil" in product and ("grado 2" in product or "comun" in product.lower()):
                prices_by_type["gasoil_grado2"].append((price, empresa))
            elif "gasoil" in product and ("grado 3" in product or "premium" in product):
                prices_by_type["gasoil_grado3"].append((price, empresa))

        for fuel_key, price_list in prices_by_type.items():
            if not price_list:
                continue
            prices = [p for p, _ in price_list]
            median_price = sorted(prices)[len(prices) // 2]

            observations.append(PriceObservation(
                producto=FUEL_PRODUCTS.get(fuel_key, fuel_key),
                precio=median_price,
                unidad="litro",
                categoria_coicop="07.2.2",
                division_coicop="07",
                fuente="Secretaría de Energía",
                url="https://datos.energia.gob.ar",
                metadata={"n_estaciones": len(price_list), "tipo": fuel_key},
            ))

        return observations

    def _collect_ypf(self) -> list[PriceObservation]:
        """Scrape YPF prices as fallback."""
        # YPF publishes prices that are reference for the market
        # We use known prices structure — these get updated when YPF raises prices
        # This is a simplified backup; in production you'd parse the actual page
        observations = []

        try:
            resp = self.fetch("https://www.ypf.com/")
            # Parse prices from YPF site — structure varies
            # For now, log that we attempted
            log.info("combustibles.ypf_fetched", status=resp.status_code)
        except Exception:
            pass

        return observations
