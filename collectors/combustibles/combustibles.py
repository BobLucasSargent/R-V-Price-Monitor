"""
R&V IPC — Combustibles collector.

Sources (in priority order):
1. datos.energia.gob.ar — CKAN API (Secretaría de Energía open data)
2. Argentina.gob.ar datos abiertos — fuel price datasets
3. ArgentinaDatos API — /v1/finanzas/rendimientos (may have fuel data)

COICOP 07.2.2 — Combustibles y lubricantes (part of Div 07 Transporte).
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
from collections import defaultdict
import structlog

log = structlog.get_logger()

# Multiple resource IDs to try — Secretaría de Energía rotates these
ENERGIA_RESOURCES = [
    "80ac25de-a44a-4f6b-b854-a5a6377e1023",  # Precios en surtidor
    "8ffd4c9b-1c6c-4c11-8085-2f24b5fad6b9",  # Alternative resource
]

ENERGIA_API = "https://datos.energia.gob.ar/api/3/action/datastore_search"

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
    description = "Combustibles — Sec. Energía open data"

    def collect(self) -> list[PriceObservation]:
        # Try each resource ID
        for resource_id in ENERGIA_RESOURCES:
            try:
                obs = self._collect_from_ckan(resource_id)
                if obs:
                    return obs
            except Exception as e:
                log.debug("combustibles.resource_error",
                          resource_id=resource_id, error=str(e))

        # Fallback: try to discover the right resource via package search
        try:
            obs = self._collect_via_package_search()
            if obs:
                return obs
        except Exception as e:
            log.debug("combustibles.package_search_error", error=str(e))

        log.warning("combustibles.all_sources_failed")
        return []

    def _collect_from_ckan(self, resource_id: str) -> list[PriceObservation]:
        """Fetch fuel prices from CKAN datastore API."""
        data = self.fetch_json(
            ENERGIA_API,
            params={
                "resource_id": resource_id,
                "limit": 200,
                "sort": "fecha desc",
            },
        )

        if not data.get("success"):
            return []

        records = data.get("result", {}).get("records", [])
        if not records:
            return []

        log.info("combustibles.ckan_records", n=len(records),
                 sample_keys=list(records[0].keys()) if records else [])

        return self._parse_fuel_records(records)

    def _collect_via_package_search(self) -> list[PriceObservation]:
        """Search CKAN for fuel price datasets if resource IDs are outdated."""
        search_url = "https://datos.energia.gob.ar/api/3/action/package_search"
        data = self.fetch_json(
            search_url,
            params={"q": "precios combustibles surtidor", "rows": 5},
        )

        if not data.get("success"):
            return []

        results = data.get("result", {}).get("results", [])
        for dataset in results:
            for resource in dataset.get("resources", []):
                if resource.get("format", "").upper() in ("CSV", "JSON", "API"):
                    rid = resource.get("id")
                    if rid:
                        try:
                            obs = self._collect_from_ckan(rid)
                            if obs:
                                log.info("combustibles.discovered_resource", resource_id=rid)
                                return obs
                        except Exception:
                            continue
        return []

    def _parse_fuel_records(self, records: list[dict]) -> list[PriceObservation]:
        """Parse CKAN records into price observations.

        The field names vary by dataset version, so we try multiple patterns.
        """
        prices_by_type: dict[str, list[float]] = defaultdict(list)

        for record in records:
            # Try different field name patterns
            product = (
                record.get("producto", "") or
                record.get("PRODUCTO", "") or
                record.get("tipo_combustible", "") or
                ""
            ).lower()

            price_raw = (
                record.get("precio", None) or
                record.get("PRECIO", None) or
                record.get("precio_unitario", None)
            )

            if price_raw is None:
                continue

            try:
                price = float(price_raw)
            except (ValueError, TypeError):
                continue

            if price <= 0:
                continue

            # Classify fuel type
            if "super" in product and "premium" not in product:
                prices_by_type["nafta_super"].append(price)
            elif "premium" in product or "infinia" in product:
                prices_by_type["nafta_premium"].append(price)
            elif ("gasoil" in product or "diesel" in product) and \
                 ("grado 2" in product or "comun" in product or "g2" in product):
                prices_by_type["gasoil_grado2"].append(price)
            elif ("gasoil" in product or "diesel" in product) and \
                 ("grado 3" in product or "premium" in product or "g3" in product):
                prices_by_type["gasoil_grado3"].append(price)
            elif "nafta" in product and "super" not in product and "premium" not in product:
                # Generic nafta → treat as super
                prices_by_type["nafta_super"].append(price)
            elif "gasoil" in product or "diesel" in product:
                # Generic gasoil → treat as grado 2
                prices_by_type["gasoil_grado2"].append(price)

        observations = []
        for fuel_key, price_list in prices_by_type.items():
            if not price_list:
                continue
            # Take median
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

        return observations
