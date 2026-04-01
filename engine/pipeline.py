"""
R&V IPC — Pipeline principal.

Orquesta todo el flujo:
1. Ejecutar collectors → precios crudos
2. Agregar precios por variedad COICOP (media geométrica)
3. Calcular variaciones vs período anterior
4. Agregar a nivel división con Laspeyres (pesos GBA)
5. Empalmar con último IPC oficial
6. Persistir resultados
7. Comparar con INDEC cuando hay dato nuevo
"""
from datetime import date, timedelta
from collections import defaultdict
import structlog

# Import collectors package to trigger @register_collector decorators
import collectors  # noqa: F401

from collectors.base import PriceObservation
from collectors.registry import get_all_collectors, get_collector, list_collectors
from engine.calculator import (
    media_geometrica, variacion_porcentual, laspeyres,
    calcular_indice_nivel_general, inflacion_anualizada,
)
from config.canasta import DIVISIONES, EXCLUIDAS, get_all_weights, get_divisiones_activas, covered_weight
from config.ipc_oficial import (
    IPC_DIVISIONES_FEB2026, EMPALME_FECHA, EMPALME_NIVEL_GENERAL,
)

log = structlog.get_logger()


def run_pipeline(
    fecha: date | None = None,
    periodo_tipo: str = "diario",
    collectors_ids: list[str] | None = None,
) -> dict:
    """
    Ejecuta el pipeline completo de R&V IPC.

    Args:
        fecha: Fecha de cálculo (default: hoy)
        periodo_tipo: "diario", "semanal", "mensual"
        collectors_ids: Lista de collectors a ejecutar (None = todos)

    Returns:
        dict con resultados del índice.
    """
    fecha = fecha or date.today()
    log.info("pipeline.start", fecha=str(fecha), periodo=periodo_tipo)

    # ── Step 1: Collect prices ──────────────────────────────────────────
    all_observations = collect_prices(collectors_ids)

    if not all_observations:
        log.warning("pipeline.no_observations")
        return {"fecha": str(fecha), "error": "No se obtuvieron precios"}

    log.info("pipeline.collected", n_total=len(all_observations))

    # ── Step 2: Group by division and compute geometric means ───────────
    precios_por_division = group_by_division(all_observations)
    promedios_division = {}

    for div_code, precios in precios_por_division.items():
        if precios:
            promedios_division[div_code] = media_geometrica(precios)

    log.info("pipeline.averages", divisiones_con_datos=list(promedios_division.keys()))

    # ── Step 3: Load previous period prices for variation calc ──────────
    # In production, this comes from DB. For bootstrap, use empalme data.
    precios_anteriores = _get_previous_prices(fecha, periodo_tipo)

    # ── Step 4: Calculate variations by division ────────────────────────
    variaciones = {}
    for div_code, precio_actual in promedios_division.items():
        precio_anterior = precios_anteriores.get(div_code)
        if precio_anterior and precio_anterior > 0:
            variaciones[div_code] = variacion_porcentual(precio_actual, precio_anterior)
        else:
            # First run — no previous data yet. Use 0.
            variaciones[div_code] = 0.0

    # ── Step 5: Calculate index via Laspeyres + empalme ─────────────────
    indices_base = _get_base_indices(fecha)
    resultado = calcular_indice_nivel_general(variaciones, indices_base)

    # ── Step 6: Build output ────────────────────────────────────────────
    ng = resultado["nivel_general"]
    ng_anterior = EMPALME_NIVEL_GENERAL  # For first run
    var_ng = variacion_porcentual(ng, ng_anterior)

    output = {
        "fecha": str(fecha),
        "periodo_tipo": periodo_tipo,
        "nivel_general": round(ng, 2),
        "variacion_periodo": round(var_ng, 2),
        "inflacion_anualizada": round(inflacion_anualizada(var_ng), 1),
        "divisiones": {},
        "cobertura_pct": round(covered_weight(), 1),
        "n_precios_recolectados": len(all_observations),
        "divisiones_con_datos": len(variaciones),
        "es_oficial": False,
    }

    for div in DIVISIONES:
        cod = div.codigo
        idx_nuevo = resultado["indices_division"].get(cod, 0)
        idx_base = indices_base.get(cod, 0)
        var = variaciones.get(cod)
        excluida = cod in EXCLUIDAS

        output["divisiones"][cod] = {
            "nombre": div.nombre_corto,
            "peso": div.peso_gba,
            "peso_ajustado": get_all_weights().get(cod, 0),
            "indice": round(idx_nuevo, 2),
            "variacion": round(var, 2) if var is not None else None,
            "tiene_datos": cod in variaciones and var != 0.0,
            "excluida": excluida,
        }

    log.info(
        "pipeline.complete",
        nivel_general=output["nivel_general"],
        variacion=output["variacion_periodo"],
        n_precios=output["n_precios_recolectados"],
    )

    return output


def collect_prices(collectors_ids: list[str] | None = None) -> list[PriceObservation]:
    """Run collectors and gather all price observations."""
    observations = []

    if collectors_ids:
        collectors = [get_collector(cid) for cid in collectors_ids]
    else:
        collectors = get_all_collectors()

    for collector in collectors:
        try:
            obs = collector.run()
            observations.extend(obs)
        except Exception as e:
            log.error("pipeline.collector_error",
                      collector=collector.collector_id, error=str(e))

    return observations


def group_by_division(observations: list[PriceObservation]) -> dict[str, list[float]]:
    """Group prices by COICOP division."""
    by_division = defaultdict(list)
    for obs in observations:
        div = obs.division_coicop
        if div and obs.precio > 0:
            by_division[div].append(obs.precio)
    return dict(by_division)


def group_by_variedad(observations: list[PriceObservation]) -> dict[str, list[float]]:
    """Group prices by COICOP variedad (finer granularity)."""
    by_variedad = defaultdict(list)
    for obs in observations:
        cat = obs.categoria_coicop
        if cat and obs.precio > 0:
            by_variedad[cat].append(obs.precio)
    return dict(by_variedad)


def _get_base_indices(fecha: date) -> dict[str, float]:
    """
    Get base indices for empalme.

    For first run, uses IPC oficial feb 2026.
    In production, loads from DB (last calculated index).
    """
    # TODO: Load from DB if available
    return dict(IPC_DIVISIONES_FEB2026)


def _get_previous_prices(fecha: date, periodo_tipo: str) -> dict[str, float]:
    """
    Get previous period average prices by division.

    For first run, returns empty (triggering 0% variation).
    In production, loads from DB.
    """
    # TODO: Load from DB
    return {}


def run_weekly_pipeline(fecha: date | None = None) -> dict:
    """Convenience wrapper for weekly index."""
    return run_pipeline(fecha=fecha, periodo_tipo="semanal")


def run_monthly_pipeline(fecha: date | None = None) -> dict:
    """Convenience wrapper for monthly index."""
    return run_pipeline(fecha=fecha, periodo_tipo="mensual")
