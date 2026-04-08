"""
R&V IPC — Alquileres collector v2 (httpx — sin Playwright).

Estrategia:
  1. ZonaProp — httpx directo, extrae JSON embebido en __NEXT_DATA__ del HTML.
     ZonaProp renderiza listados en SSR, por lo que el HTML contiene los precios
     sin necesidad de ejecutar JS.
  2. Fallback — Mercado Libre Inmuebles API pública (sin auth, sin bloqueo conocido
     en Railway).

Cubre COICOP 04.1.1 — Alquiler de vivienda (~11.8% del IPC).
"""

from __future__ import annotations

import json
import re
import statistics
from typing import Optional

import httpx
import structlog

from collectors.base import BaseCollector, PriceObservation
from collectors.registry import register_collector

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Configuración de perfiles de búsqueda
# ---------------------------------------------------------------------------

ZONAPROP_PROFILES = [
    {
        "desc": "2 amb CABA",
        "url": "https://www.zonaprop.com.ar/departamentos-alquiler-capital-federal-2-ambientes.html",
        "coicop": "04.1.1",
    },
    {
        "desc": "3 amb CABA",
        "url": "https://www.zonaprop.com.ar/departamentos-alquiler-capital-federal-3-ambientes.html",
        "coicop": "04.1.1",
    },
    {
        "desc": "2 amb GBA Norte",
        "url": "https://www.zonaprop.com.ar/departamentos-alquiler-zona-norte-2-ambientes.html",
        "coicop": "04.1.1",
    },
]

# MercadoLibre Inmuebles: site AR = MLA, category MLA1459 = Departamentos en alquiler
MLA_PROFILES = [
    {
        "desc": "2 amb CABA",
        "url": (
            "https://api.mercadolibre.com/sites/MLA/search"
            "?category=MLA1459"
            "&state=TUxBUENBUGw3M2E1"   # Capital Federal
            "&BEDROOMS=2"
            "&price=100000-5000000"
            "&limit=20"
        ),
        "coicop": "04.1.1",
    },
    {
        "desc": "3 amb CABA",
        "url": (
            "https://api.mercadolibre.com/sites/MLA/search"
            "?category=MLA1459"
            "&state=TUxBUENBUGw3M2E1"
            "&BEDROOMS=3"
            "&price=100000-5000000"
            "&limit=20"
        ),
        "coicop": "04.1.1",
    },
    {
        "desc": "2 amb GBA",
        "url": (
            "https://api.mercadolibre.com/sites/MLA/search"
            "?category=MLA1459"
            "&state=TUxBUFpBUnA3MWU1"   # Buenos Aires (provincia)
            "&BEDROOMS=2"
            "&price=100000-5000000"
            "&limit=20"
        ),
        "coicop": "04.1.1",
    },
]

# Sanity bounds para ARS/mes — alquileres residenciales 2025-2026
RENT_MIN = 150_000
RENT_MAX = 8_000_000

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_price(text: str) -> Optional[float]:
    """Extraer número de strings tipo '$1.200.000' o '1200000'."""
    if not text:
        return None
    # Descartar USD
    if any(tok in text.upper() for tok in ("USD", "U$S", "U$D", "DOLAR", "DÓLAR")):
        return None
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    value = float(digits)
    return value if RENT_MIN <= value <= RENT_MAX else None


def _median_or_none(prices: list[float]) -> Optional[float]:
    if not prices:
        return None
    return statistics.median(prices)


# ---------------------------------------------------------------------------
# ZonaProp via __NEXT_DATA__
# ---------------------------------------------------------------------------

def _fetch_zonaprop_profile(client: httpx.Client, profile: dict) -> list[float]:
    """
    ZonaProp usa Next.js SSR — el HTML contiene __NEXT_DATA__ con los listings
    en formato JSON. No se necesita renderizar JS.
    """
    try:
        r = client.get(profile["url"], timeout=20)
        r.raise_for_status()
    except Exception as e:
        log.debug("alquileres.zonaprop_http_error", profile=profile["desc"], error=str(e))
        return []

    # Extraer bloque __NEXT_DATA__
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
    if not match:
        log.debug("alquileres.zonaprop_no_next_data", profile=profile["desc"])
        return []

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        log.debug("alquileres.zonaprop_json_error", profile=profile["desc"], error=str(e))
        return []

    prices: list[float] = []

    # Navegar la estructura de Next.js — ZonaProp guarda listings bajo
    # props.pageProps.listPostings o props.pageProps.initialSearchResults
    try:
        page_props = data["props"]["pageProps"]

        # Intentar múltiples paths conocidos de ZonaProp
        listings_candidates = [
            page_props.get("listPostings", []),
            page_props.get("initialSearchResults", {}).get("listPostings", []),
            page_props.get("searchResults", {}).get("listPostings", []),
        ]

        for listings in listings_candidates:
            if not listings:
                continue
            for listing in listings[:30]:
                # El precio puede estar en distintas keys según versión de ZonaProp
                for price_path in [
                    ["postingLocation", "price", "amount"],
                    ["price", "amount"],
                    ["priceOperationTypes", 0, "prices", 0, "amount"],
                ]:
                    try:
                        val = listing
                        for key in price_path:
                            val = val[key]
                        p = _parse_price(str(val))
                        if p:
                            prices.append(p)
                            break
                    except (KeyError, IndexError, TypeError):
                        continue
            if prices:
                break  # salir si encontramos precios con este path

    except (KeyError, TypeError) as e:
        log.debug("alquileres.zonaprop_parse_error", profile=profile["desc"], error=str(e))

    # Si no encontramos en estructura JSON, intentar regex sobre el HTML completo
    # como último recurso (precios ARS en texto)
    if not prices:
        raw_prices = re.findall(r'\$\s*([\d.,]{6,})', r.text)
        for raw in raw_prices[:40]:
            p = _parse_price(raw)
            if p:
                prices.append(p)

    log.debug("alquileres.zonaprop_prices", profile=profile["desc"], n=len(prices))
    return prices


# ---------------------------------------------------------------------------
# MercadoLibre Inmuebles (fallback)
# ---------------------------------------------------------------------------

def _fetch_mla_profile(client: httpx.Client, profile: dict) -> list[float]:
    """
    MercadoLibre Inmuebles tiene API pública sin auth.
    Devuelve JSON con campo results[].price en ARS.
    """
    try:
        r = client.get(
            profile["url"],
            timeout=20,
            headers={
                "User-Agent": "RyV-IPC-Collector/1.0",
                "Accept": "application/json",
            },
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.debug("alquileres.mla_http_error", profile=profile["desc"], error=str(e))
        return []

    prices: list[float] = []
    for item in data.get("results", []):
        try:
            currency = item.get("currency_id", "")
            if currency != "ARS":
                continue
            p = _parse_price(str(item["price"]))
            if p:
                prices.append(p)
        except (KeyError, TypeError):
            continue

    log.debug("alquileres.mla_prices", profile=profile["desc"], n=len(prices))
    return prices


# ---------------------------------------------------------------------------
# Collector principal
# ---------------------------------------------------------------------------

@register_collector
class AlquileresCollector(BaseCollector):
    collector_id = "alquileres"
    division_coicop = "04"
    description = "Alquileres residenciales — ZonaProp (httpx/__NEXT_DATA__) + fallback MercadoLibre Inmuebles"

    def collect(self) -> list[PriceObservation]:
        observations: list[PriceObservation] = []

        with httpx.Client(headers=HEADERS_BROWSER, timeout=25, follow_redirects=True) as client:

            # ── Intento 1: ZonaProp ──────────────────────────────────────────
            zonaprop_ok = 0
            for profile in ZONAPROP_PROFILES:
                prices = _fetch_zonaprop_profile(client, profile)
                median = _median_or_none(prices)
                if median:
                    observations.append(
                        PriceObservation(
                            producto=f"Alquiler {profile['desc']}",
                            precio=median,
                            unidad="ARS/mes",
                            categoria_coicop=profile["coicop"],
                            division_coicop="04",
                            fuente="ZonaProp",
                            url=profile["url"],
                            metadata={
                                "n_listings": len(prices),
                                "profile": profile["desc"],
                                "min": min(prices),
                                "max": max(prices),
                                "source_layer": "zonaprop_next_data",
                            },
                        )
                    )
                    zonaprop_ok += 1

            if zonaprop_ok > 0:
                log.info("alquileres.zonaprop_success", n_profiles=zonaprop_ok)
                return observations  # ZonaProp funcionó, no necesitamos fallback

            # ── Intento 2: MercadoLibre Inmuebles (fallback) ─────────────────
            log.info("alquileres.zonaprop_failed_using_mla_fallback")
            for profile in MLA_PROFILES:
                prices = _fetch_mla_profile(client, profile)
                median = _median_or_none(prices)
                if median:
                    observations.append(
                        PriceObservation(
                            producto=f"Alquiler {profile['desc']}",
                            precio=median,
                            unidad="ARS/mes",
                            categoria_coicop=profile["coicop"],
                            division_coicop="04",
                            fuente="MercadoLibre Inmuebles",
                            url=profile["url"],
                            metadata={
                                "n_listings": len(prices),
                                "profile": profile["desc"],
                                "min": min(prices),
                                "max": max(prices),
                                "source_layer": "mercadolibre_api",
                            },
                        )
                    )

            if not observations:
                log.warning("alquileres.all_sources_failed")

            return observations
