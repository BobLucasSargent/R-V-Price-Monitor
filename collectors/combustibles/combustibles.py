"""
R&V IPC — Combustibles collector.

Source: datos.energia.gob.ar — CKAN API (Secretaría de Energía open data)
Dataset: "Precios en Surtidor - Resolución 314/2016"

Resource ID for "Precios vigentes": 80ac25de-a44a-4445-9215-090cf55cfda5

COICOP 07.2.2 — Combustibles y lubricantes (part of Div 07 Transporte).
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
from collections import defaultdict
import structlog

log = structlog.get_logger()

ENERGIA_API = "https://datos.energia.gob.ar/api/3/action/datastore_search"

# Correct resource ID for "Precios vigentes en surtidor"
RESOURCE_VIGENTES = "80ac25de-a44a-4445-9215-090cf55cfda5"

FUEL_PRODUCTS = {
    "nafta_super": "Nafta Súper (Grado 2)",
    "nafta_premium": "Nafta Premium (Grado 3)",
    "gasoil_grado2": "Gasoil Grado 2",
    "gasoil_grado3": "Gasoil Grado 3",
    "gnc": "GNC",
}


@register_collector
class CombustiblesCollector(BaseCollector):
    collector_id = "combustibles"
    division_coicop = "07"
    description = "Combustibles — Sec. Energía (datos.energia.gob.ar)"

    def collect(self) -> list[PriceObservation]:
        # Try direct resource first
        obs = self._collect_from_resource(RESOURCE_VIGENTES)
        if obs:
            return obs

        # Fallback: discover resource via package_show
        obs = self._collect_via_discovery()
        if obs:
            return obs

        log.warning("combustibles.all_sources_failed")
        return []

    def _collect_from_resource(self, resource_id: str) -> list[PriceObservation]:
        """Fetch fuel prices from a specific CKAN resource."""
        try:
            data = self.fetch_json(
                ENERGIA_API,
                params={
                    "resource_id": resource_id,
                    "limit": 500,
                },
            )

            if not isinstance(data, dict) or not data.get("success"):
                log.debug("combustibles.resource_not_success", resource_id=resource_id)
                return []

            records = data.get("result", {}).get("records", [])
            if not records:
                log.debug("combustibles.no_records", resource_id=resource_id)
                return []

            # Log field names for debugging
            log.info("combustibles.fields_found",
                     keys=list(records[0].keys()) if records else [],
                     n_records=len(records))

            return self._parse_records(records)

        except Exception as e:
            log.debug("combustibles.resource_error",
                      resource_id=resource_id, error=str(e))
            return []

    def _collect_via_discovery(self) -> list[PriceObservation]:
        """Discover the right resource via package_show."""
        try:
            pkg = self.fetch_json(
                "https://datos.energia.gob.ar/api/3/action/package_show",
                params={"id": "precios-en-surtidor"},
            )

            if not pkg.get("success"):
                return []

            resources = pkg.get("result", {}).get("resources", [])
            for r in resources:
                name = (r.get("name", "") or r.get("description", "")).lower()
                if "vigente" in name:
                    rid = r.get("id")
                    if rid:
                        log.info("combustibles.discovered_resource",
                                 resource_id=rid, name=name)
                        obs = self._collect_from_resource(rid)
                        if obs:
                            return obs

        except Exception as e:
            log.debug("combustibles.discovery_error", error=str(e))

        return []

    def _parse_records(self, records: list[dict]) -> list[PriceObservation]:
        """Parse CKAN records into price observations.

        Field names from datos.energia.gob.ar:
        - producto: "Nafta (grado 2)", "Nafta (grado 3)", "Gasoil (grado 2)", etc.
        - precio: float in ARS/litro
        - empresa / empresabandera: "YPF", "Shell", etc.
        - provincia: "BUENOS AIRES", etc.
        - localidad: city name
        """
        prices_by_type: dict[str, list[float]] = defaultdict(list)

        for record in records:
            # Try multiple field name patterns
            product = ""
            for key in ["producto", "PRODUCTO", "tipo_combustible", "descripcion"]:
                val = record.get(key)
                if val:
                    product = str(val).lower()
                    break

            price_raw = None
            for key in ["precio", "PRECIO", "precio_unitario", "precioventa"]:
                val = record.get(key)
                if val is not None:
                    price_raw = val
                    break

            if not product or price_raw is None:
                continue

            try:
                price = float(price_raw)
            except (ValueError, TypeError):
                continue

            if price <= 0 or price > 10000:  # Sanity: ARS/litro
                continue

            # Filter to Buenos Aires / GBA if possible
            provincia = ""
            for key in ["provincia", "PROVINCIA", "idprovincia"]:
                val = record.get(key)
                if val:
                    provincia = str(val).upper()
                    break

            # Only GBA prices if province field exists
            if provincia and "BUENOS AIRES" not in provincia and "CAPITAL" not in provincia:
                continue

            # Classify fuel type
            if ("grado 2" in product or "grado2" in product) and "nafta" in product:
                prices_by_type["nafta_super"].append(price)
            elif ("grado 3" in product or "grado3" in product) and "nafta" in product:
                prices_by_type["nafta_premium"].append(price)
            elif "nafta" in product and "super" in product:
                prices_by_type["nafta_super"].append(price)
            elif "nafta" in product and ("premium" in product or "infinia" in product):
                prices_by_type["nafta_premium"].append(price)
            elif ("grado 2" in product or "grado2" in product) and ("gasoil" in product or "diesel" in product):
                prices_by_type["gasoil_grado2"].append(price)
            elif ("grado 3" in product or "grado3" in product) and ("gasoil" in product or "diesel" in product):
                prices_by_type["gasoil_grado3"].append(price)
            elif "gnc" in product or "gas natural" in product:
                prices_by_type["gnc"].append(price)
            elif "nafta" in product:
                prices_by_type["nafta_super"].append(price)
            elif "gasoil" in product or "diesel" in product:
                prices_by_type["gasoil_grado2"].append(price)

        observations = []
        for fuel_key, price_list in prices_by_type.items():
            if not price_list:
                continue
            sorted_prices = sorted(price_list)
            median_price = sorted_prices[len(sorted_prices) // 2]

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

        if observations:
            log.info("combustibles.parsed_ok", n_products=len(observations),
                     types=list(prices_by_type.keys()))

        return observations
