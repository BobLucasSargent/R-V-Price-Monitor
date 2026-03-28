"""
R&V IPC — Financial variables collector.

Uses ArgentinaDatos API (free, public, reliable) for:
- Dollar exchange rates (oficial, blue, MEP, CCL)
- Inflation (official INDEC data — for comparison)

API docs: https://argentinadatos.com/docs/
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
import structlog
from datetime import date

log = structlog.get_logger()

API_BASE = "https://api.argentinadatos.com/v1"


@register_collector
class DolarCollector(BaseCollector):
    collector_id = "dolar"
    division_coicop = ""  # Auxiliary variable, not COICOP
    description = "Dólar y variables financieras — ArgentinaDatos API"

    def collect(self) -> list[PriceObservation]:
        observations = []

        # Fetch dollar rates
        for tipo in ["oficial", "blue", "bolsa", "contadoconliqui"]:
            try:
                data = self.fetch_json(f"{API_BASE}/cotizaciones/dolares/{tipo}")
                if isinstance(data, list) and data:
                    latest = data[-1]
                    venta = latest.get("venta")
                    compra = latest.get("compra")
                    fecha_str = latest.get("fecha", str(date.today()))

                    if venta:
                        observations.append(PriceObservation(
                            producto=f"Dólar {tipo} (venta)",
                            precio=float(venta),
                            unidad="ARS/USD",
                            fuente="ArgentinaDatos",
                            url=f"{API_BASE}/cotizaciones/dolares/{tipo}",
                            metadata={"tipo": tipo, "compra": compra},
                        ))
            except Exception as e:
                log.warning("dolar.tipo_error", tipo=tipo, error=str(e))

        return observations
