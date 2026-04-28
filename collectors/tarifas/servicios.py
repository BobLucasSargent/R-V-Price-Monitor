"""
R&V IPC — Tarifas de servicios públicos (referencia hardcodeada).

Covers COICOP 04.4/04.5:
- 04.5.1 Electricidad
- 04.5.2 Gas natural
- 04.4   Agua potable

Las tarifas cambian discretamente cada 2-3 meses por resolución regulatoria.
No tiene sentido scrapearlas diariamente — se actualizan manualmente acá
cuando ENRE/ENARGAS/ERAS publican nuevas resoluciones.

Última actualización: marzo 2026
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

# Tarifas de referencia para hogar residencial típico GBA
# Actualizar manualmente cuando cambien las resoluciones tarifarias
TARIFAS_REFERENCIA = {
    "electricidad": {
        "nombre": "Electricidad Edenor — consumo medio residencial (350 kWh/bim)",
        "precio": 32900,
        "coicop": "04.5.1",
        "fuente": "ENRE / Edenor (referencia)",
        "url": "https://www.edenor.com.ar/tarifas",
    },
    "gas": {
        "nombre": "Gas natural Metrogas — consumo medio residencial",
        "precio": 28000.0,
        "coicop": "04.5.2",
        "fuente": "ENARGAS / Metrogas (referencia)",
        "url": "https://www.metrogas.com.ar/tarifas",
    },
    "agua": {
        "nombre": "Agua y saneamiento AySA",
        "precio": 12000.0,
        "coicop": "04.4",
        "fuente": "AySA / ERAS (referencia)",
        "url": "https://www.aysa.com.ar/usuarios/Factura-y-Consumo",
    },
}


@register_collector
class TarifasCollector(BaseCollector):
    collector_id = "tarifas"
    division_coicop = "04"
    description = "Tarifas servicios públicos — Electricidad, gas, agua (referencia regulatoria)"

    def collect(self) -> list[PriceObservation]:
        observations = []

        for key, tarifa in TARIFAS_REFERENCIA.items():
            observations.append(PriceObservation(
                producto=tarifa["nombre"],
                precio=tarifa["precio"],
                unidad="ARS/mes",
                categoria_coicop=tarifa["coicop"],
                division_coicop="04",
                fuente=tarifa["fuente"],
                url=tarifa["url"],
                metadata={"tipo": key, "es_referencia": True},
            ))

        log.info("tarifas.collected", n=len(observations))
        return observations
