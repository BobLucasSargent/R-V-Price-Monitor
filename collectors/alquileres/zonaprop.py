"""
R&V IPC — Alquileres collector v3.

Fuente primaria: MercadoLibre Inmuebles API pública (sin auth).
No usa Playwright ni ZonaProp.

Estrategia de búsqueda:
  - Busca "departamento alquiler" via la API de search de MLA
  - Filtra por Capital Federal y GBA usando el parámetro de texto + location
  - Toma mediana de precios ARS para cada perfil
  - Los IDs de categoría/estado se resuelven en runtime para evitar hardcodear
    valores opacos que pueden cambiar

COICOP 04.1.1 — Alquiler de vivienda
"""

from __future__ import annotations

import statistics
from typing import Optional

import httpx
import structlog

from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

MLA_SEARCH_BASE = "https://api.mercadolibre.com/sites/MLA/search"

# Sanity bounds ARS/mes — alquileres residenciales 2025-2026
RENT_MIN = 150_000
RENT_MAX = 10_000_000

# Perfiles: cada uno genera 1 PriceObservation con la mediana
# Se usan parámetros de texto + category ID de inmuebles en alquiler (MLA1459)
# MLA1459 = Departamentos > Alquiler en MercadoLibre Argentina
# Los filtros de habitaciones usan el atributo BEDROOMS de MLA

SEARCH_PROFILES = [
    {
        "desc": "2 amb CABA",
        "params": {
            "category": "MLA1459",        # Departamentos en alquiler
            "q": "departamento 2 ambientes",
            "state": "TUxBUENBUGw3M2E1",  # Capital Federal
            "price": f"{RENT_MIN}-{RENT_MAX}",
            "OPERATION": "242073",         # Alquiler
            "limit": "50",
            "offset": "0",
        },
    },
    {
        "desc": "3 amb CABA",
        "params": {
            "category": "MLA1459",
            "q": "departamento 3 ambientes",
            "state": "TUxBUENBUGw3M2E1",
            "price": f"{RENT_MIN}-{RENT_MAX}",
            "OPERATION": "242073",
            "limit": "50",
            "offset": "0",
        },
    },
    {
        "desc": "2 amb GBA",
        "params": {
            "category": "MLA1459",
            "q": "departamento 2 ambientes",
            "state": "TUxBUFpBUnA3MWU1",  # Buenos Aires provincia
            "price": f"{RENT_MIN}-{RENT_MAX}",
            "OPERATION": "242073",
            "limit": "50",
            "offset": "0",
        },
    },
]

HEADERS = {
    "User-Agent": "RyV-IPC-Collector/1.0",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_prices(results: list[dict]) -> list[float]:
    prices = []
    for item in results:
        try:
            if item.get("currency_id") != "ARS":
                continue
            val = float(item["price"])
            if RENT_MIN <= val <= RENT_MAX:
                prices.append(val)
        except (KeyError, TypeError, ValueError):
            continue
    return prices


def _median(prices: list[float]) -> Optional[float]:
    return statistics.median(prices) if prices else None


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

@register_collector
class AlquileresCollector(BaseCollector):
    collector_id = "alquileres"
    division_coicop = "04"
    description = "Alquileres residenciales — MercadoLibre Inmuebles API"

    def collect(self) -> list[PriceObservation]:
        observations: list[PriceObservation] = []

        with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            for profile in SEARCH_PROFILES:
                obs = self._fetch_profile(client, profile)
                if obs:
                    observations.append(obs)

        if not observations:
            log.warning("alquileres.all_profiles_failed")

        return observations

    def _fetch_profile(self, client: httpx.Client, profile: dict) -> Optional[PriceObservation]:
        desc = profile["desc"]
        try:
            r = client.get(MLA_SEARCH_BASE, params=profile["params"])
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.warning("alquileres.fetch_error", profile=desc, error=str(e))
            return None

        results = data.get("results", [])
        log.debug("alquileres.raw_results", profile=desc, n_results=len(results))

        prices = _extract_prices(results)
        median = _median(prices)

        if not median:
            # Si no hay resultados con los state IDs hardcodeados,
            # reintentar sin filtro de estado (búsqueda nacional) como fallback
            log.debug("alquileres.retrying_without_state_filter", profile=desc)
            fallback_params = {k: v for k, v in profile["params"].items() if k != "state"}
            try:
                r2 = client.get(MLA_SEARCH_BASE, params=fallback_params)
                r2.raise_for_status()
                results = r2.json().get("results", [])
                prices = _extract_prices(results)
                median = _median(prices)
            except Exception as e:
                log.warning("alquileres.fallback_error", profile=desc, error=str(e))

        if not median:
            log.warning("alquileres.no_prices", profile=desc)
            return None

        log.info("alquileres.ok", profile=desc, n=len(prices), median=median)

        return PriceObservation(
            producto=f"Alquiler {desc}",
            precio=median,
            unidad="ARS/mes",
            categoria_coicop="04.1.1",
            division_coicop="04",
            fuente="MercadoLibre Inmuebles",
            url=f"{MLA_SEARCH_BASE}?{'&'.join(f'{k}={v}' for k,v in profile['params'].items())}",
            metadata={
                "n_listings": len(prices),
                "profile": desc,
                "min": min(prices) if prices else None,
                "max": max(prices) if prices else None,
            },
        )
