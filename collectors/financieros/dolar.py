"""
R&V IPC — Dólar and financial variables collector.

Sources (in priority order):
1. ArgentinaDatos API — https://api.argentinadatos.com
2. DolarAPI — https://dolarapi.com (fallback)

Provides: oficial, blue, MEP (bolsa), CCL exchange rates.
These are auxiliary variables (not COICOP) used for analysis.
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()


@register_collector
class DolarCollector(BaseCollector):
    collector_id = "dolar"
    division_coicop = ""  # Auxiliary variable, not COICOP
    description = "Dólar y variables financieras"

    def collect(self) -> list[PriceObservation]:
        observations = []

        # Try ArgentinaDatos first
        obs = self._try_argentinadatos()
        if obs:
            return obs

        # Fallback: DolarAPI
        obs = self._try_dolarapi()
        if obs:
            return obs

        log.warning("dolar.all_sources_failed")
        return observations

    def _try_argentinadatos(self) -> list[PriceObservation]:
        """ArgentinaDatos API — /v1/cotizaciones/dolares/{tipo}"""
        observations = []
        tipos = ["oficial", "blue", "bolsa", "contadoconliqui"]

        for tipo in tipos:
            try:
                data = self.fetch_json(
                    f"https://api.argentinadatos.com/v1/cotizaciones/dolares/{tipo}"
                )
                if isinstance(data, list) and data:
                    latest = data[-1]
                    venta = latest.get("venta")
                    if venta:
                        observations.append(PriceObservation(
                            producto=f"Dólar {tipo} (venta)",
                            precio=float(venta),
                            unidad="ARS/USD",
                            fuente="ArgentinaDatos",
                            url=f"https://api.argentinadatos.com/v1/cotizaciones/dolares/{tipo}",
                            metadata={"tipo": tipo, "compra": latest.get("compra")},
                        ))
            except Exception as e:
                log.debug("dolar.argentinadatos_error", tipo=tipo, error=str(e))

        if observations:
            log.info("dolar.argentinadatos_ok", n=len(observations))
        return observations

    def _try_dolarapi(self) -> list[PriceObservation]:
        """DolarAPI — https://dolarapi.com/v1/dolares"""
        observations = []
        try:
            data = self.fetch_json("https://dolarapi.com/v1/dolares")
            if not isinstance(data, list):
                return []

            tipo_map = {
                "oficial": "oficial",
                "blue": "blue",
                "bolsa": "bolsa",
                "contadoconliqui": "contadoconliqui",
                "tarjeta": "tarjeta",
            }

            for item in data:
                casa = item.get("casa", "")
                venta = item.get("venta")
                if casa in tipo_map and venta:
                    observations.append(PriceObservation(
                        producto=f"Dólar {casa} (venta)",
                        precio=float(venta),
                        unidad="ARS/USD",
                        fuente="DolarAPI",
                        url="https://dolarapi.com/v1/dolares",
                        metadata={"tipo": casa, "compra": item.get("compra")},
                    ))

            if observations:
                log.info("dolar.dolarapi_ok", n=len(observations))
        except Exception as e:
            log.warning("dolar.dolarapi_error", error=str(e))

        return observations
