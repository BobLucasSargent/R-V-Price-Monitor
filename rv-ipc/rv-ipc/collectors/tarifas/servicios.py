"""
R&V IPC — Tarifas de servicios públicos.

Covers COICOP 04.4/04.5:
- 04.5.1 Electricidad (1.03%)
- 04.5.2 Gas natural (1.51%)
- 04.4 Agua potable (0.89%)

Uses official tariff information from regulators and utilities.
Tariff changes are discrete events — prices don't change daily.
We track the current tariff and detect changes.
"""
from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector
import structlog

log = structlog.get_logger()

# Known tariff reference points (updated when tariffs change)
# These are approximate monthly bills for a typical GBA household
# Source: ENRE, ENARGAS, AySA resolution publications
TARIFAS_REFERENCIA = {
    "electricidad_edenor": {
        "nombre": "Electricidad Edenor — consumo medio residencial",
        "coicop": "04.5.1",
        "fuente_resolucion": "ENRE",
        "url_ente": "https://www.argentina.gob.ar/enre",
    },
    "gas_metrogas": {
        "nombre": "Gas natural Metrogas — consumo medio residencial",
        "coicop": "04.5.2",
        "fuente_resolucion": "ENARGAS",
        "url_ente": "https://www.enargas.gob.ar",
    },
    "agua_aysa": {
        "nombre": "Agua y saneamiento AySA",
        "coicop": "04.4",
        "fuente_resolucion": "AySA / ERAS",
        "url_ente": "https://www.aysa.com.ar",
    },
}


@register_collector
class TarifasCollector(BaseCollector):
    collector_id = "tarifas"
    division_coicop = "04"
    description = "Tarifas servicios públicos — Electricidad, gas, agua"

    def collect(self) -> list[PriceObservation]:
        observations = []

        # Try to scrape current tariff info from utility websites
        observations.extend(self._collect_edenor())
        observations.extend(self._collect_metrogas())
        observations.extend(self._collect_aysa())

        return observations

    def _collect_edenor(self) -> list[PriceObservation]:
        """Attempt to get electricity tariff from Edenor."""
        try:
            # Edenor publishes tariff schedules
            resp = self.fetch("https://www.edenor.com.ar/tarifas")
            # Parse the tariff table — structure varies by resolution
            # For now, log the attempt
            log.info("tarifas.edenor_fetched", status=resp.status_code)

            # The actual parsing requires understanding the current tariff
            # structure, which changes with each ENRE resolution.
            # A production implementation would:
            # 1. Parse the tariff table HTML
            # 2. Apply the consumption vector from INDEC methodology (sec 8.1)
            # 3. Calculate a weighted average bill

        except Exception as e:
            log.warning("tarifas.edenor_error", error=str(e))

        return []

    def _collect_metrogas(self) -> list[PriceObservation]:
        """Attempt to get gas tariff from Metrogas / ENARGAS."""
        try:
            resp = self.fetch("https://www.metrogas.com.ar/tarifas")
            log.info("tarifas.metrogas_fetched", status=resp.status_code)
        except Exception as e:
            log.warning("tarifas.metrogas_error", error=str(e))
        return []

    def _collect_aysa(self) -> list[PriceObservation]:
        """Attempt to get water tariff from AySA."""
        try:
            resp = self.fetch("https://www.aysa.com.ar/usuarios/Factura-y-Consumo")
            log.info("tarifas.aysa_fetched", status=resp.status_code)
        except Exception as e:
            log.warning("tarifas.aysa_error", error=str(e))
        return []
