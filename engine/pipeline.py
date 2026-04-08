"""
R&V IPC — Pipeline principal (con persistencia).

Flujo:
1. Ejecutar collectors → precios crudos
2. Guardar precios en PostgreSQL (precios_raw)
3. Calcular promedios geométricos por división para el mes en curso
4. Cargar promedios del mes anterior (de DB o empalme INDEC)
5. Calcular variaciones por división
6. Agregar con Laspeyres → nivel general
7. Si es fin de mes, cerrar el mes (guardar índices definitivos)
8. Devolver resultado
"""
from datetime import date, datetime, timedelta
from collections import defaultdict
import numpy as np
import structlog

# Import collectors to trigger @register_collector
import collectors  # noqa: F401

from collectors.base import PriceObservation
from collectors.registry import get_all_collectors, get_collector, list_collectors
from engine.calculator import (
    media_geometrica, variacion_porcentual, laspeyres,
    calcular_indice_nivel_general, inflacion_anualizada,
)
from config.canasta import DIVISIONES, EXCLUIDAS, get_all_weights, get_divisiones_activas
from config.ipc_oficial import IPC_DIVISIONES_FEB2026, EMPALME_NIVEL_GENERAL
from storage.repository import (
    ensure_tables, save_raw_prices, save_collector_status,
    get_monthly_avg_by_division, get_previous_month_indices,
    save_monthly_index, seed_empalme_data,
    get_price_count_by_month, get_collection_days_in_month,
    get_daily_avg_by_division, get_first_day_of_month_with_data,
    get_last_day_of_month_with_data, get_all_daily_avgs_in_month,
)

log = structlog.get_logger()


def run_pipeline(
    fecha: date | None = None,
    periodo_tipo: str = "diario",
    collectors_ids: list[str] | None = None,
) -> dict:
    """
    Execute the full R&V IPC pipeline with persistence.
    """
    fecha = fecha or date.today()
    mes_actual = fecha.strftime("%Y-%m")
    log.info("pipeline.start", fecha=str(fecha), mes=mes_actual, periodo=periodo_tipo)

    # Ensure DB tables exist and empalme is seeded
    try:
        ensure_tables()
        seed_empalme_data()
    except Exception as e:
        log.error("pipeline.db_init_error", error=str(e))
        # Continue without DB — will return in-memory results

    # ── Step 1: Collect prices ──────────────────────────────────────────
    all_observations = _collect_and_save(fecha, collectors_ids)

    if not all_observations:
        log.warning("pipeline.no_observations")
        return _build_fallback_result(fecha, mes_actual)

    log.info("pipeline.collected", n_total=len(all_observations))

    # ── Step 2: Get current month averages from DB ──────────────────────
    avg_actual = get_monthly_avg_by_division(mes_actual)

    if not avg_actual:
        # Fallback: compute from in-memory observations
        avg_actual = _compute_averages_in_memory(all_observations)

    # ── Step 3: Get previous month averages ─────────────────────────────
    mes_anterior = _previous_month(mes_actual)
    avg_anterior = get_monthly_avg_by_division(mes_anterior)

    if not avg_anterior:
        # First month — no previous data from collectors
        # Use INDEC empalme indices as proxy for "previous level"
        # We can't directly compare price levels, so we compute
        # an intra-month variation using daily data instead
        log.info("pipeline.no_previous_month_data", mes_anterior=mes_anterior)

    # ── Step 4: Calculate variations by division ────────────────────────
    variaciones = {}
    for div_code, precio_actual in avg_actual.items():
        if div_code in EXCLUIDAS:
            continue
        precio_anterior = avg_anterior.get(div_code)
        if precio_anterior and precio_anterior > 0:
            variaciones[div_code] = variacion_porcentual(precio_actual, precio_anterior)
        else:
            # No previous data for this division — can't compute variation
            variaciones[div_code] = None

    # ── Step 5: Calculate index via Laspeyres ───────────────────────────
    prev_indices = get_previous_month_indices()
    resultado = calcular_indice_nivel_general(
        {k: v for k, v in variaciones.items() if v is not None},
        prev_indices,
    )

    ng = resultado["nivel_general"]
    ng_anterior = prev_indices.get("nivel_general", EMPALME_NIVEL_GENERAL)
    var_ng = variacion_porcentual(ng, ng_anterior)

    # ── Step 6: Build output ────────────────────────────────────────────
    n_precios_mes = get_price_count_by_month(mes_actual)
    n_dias = get_collection_days_in_month(mes_actual)
    pesos = get_all_weights()

    # Count divisions with real variation data
    divs_con_datos = sum(1 for v in variaciones.values() if v is not None)

    output = {
        "fecha": str(fecha),
        "mes": mes_actual,
        "periodo_tipo": periodo_tipo,
        "nivel_general": round(ng, 2),
        "variacion_periodo": round(var_ng, 2),
        "inflacion_anualizada": round(inflacion_anualizada(var_ng), 1),
        "divisiones": {},
        "cobertura_pct": round(sum(pesos.get(k, 0) for k in variaciones if variaciones[k] is not None), 1),
        "n_precios_recolectados": len(all_observations),
        "n_precios_mes_total": n_precios_mes,
        "n_dias_recoleccion": n_dias,
        "divisiones_con_datos": divs_con_datos,
        "es_oficial": False,
        "fuente": "R&V IPC (pipeline)",
        "mes_anterior_ref": mes_anterior,
        "tiene_datos_mes_anterior": bool(avg_anterior),
    }

    for div in DIVISIONES:
        cod = div.codigo
        excluida = cod in EXCLUIDAS
        idx_nuevo = resultado["indices_division"].get(cod, 0)
        var = variaciones.get(cod)

        output["divisiones"][cod] = {
            "nombre": div.nombre_corto,
            "peso": div.peso_gba,
            "peso_ajustado": pesos.get(cod, 0),
            "indice": round(idx_nuevo, 2),
            "variacion": round(var, 2) if var is not None else None,
            "tiene_datos": var is not None,
            "excluida": excluida,
            "precio_promedio_actual": round(avg_actual.get(cod, 0), 2) if cod in avg_actual else None,
            "precio_promedio_anterior": round(avg_anterior.get(cod, 0), 2) if cod in avg_anterior else None,
        }

    log.info(
        "pipeline.complete",
        nivel_general=output["nivel_general"],
        variacion=output["variacion_periodo"],
        n_precios=output["n_precios_recolectados"],
        divs_con_datos=divs_con_datos,
    )

    return output


def close_month(mes: str) -> dict:
    """
    Close a month: compute final monthly index and save to DB.
    Called automatically when a new month starts, or manually.

    Args:
        mes: "YYYY-MM" to close (e.g. "2026-03")

    Returns:
        Summary of closed month.
    """
    log.info("pipeline.closing_month", mes=mes)

    ensure_tables()
    seed_empalme_data()

    avg_actual = get_monthly_avg_by_division(mes)
    mes_anterior = _previous_month(mes)
    avg_anterior = get_monthly_avg_by_division(mes_anterior)

    if not avg_actual:
        return {"error": f"No price data for {mes}", "mes": mes}

    # Get base indices
    prev_indices = get_previous_month_indices()

    # Calculate variations
    variaciones = {}
    for div_code, precio_actual in avg_actual.items():
        if div_code in EXCLUIDAS:
            continue
        precio_anterior = avg_anterior.get(div_code)
        if precio_anterior and precio_anterior > 0:
            variaciones[div_code] = variacion_porcentual(precio_actual, precio_anterior)

    # Calculate new indices
    resultado = calcular_indice_nivel_general(
        variaciones, prev_indices,
    )

    ng = resultado["nivel_general"]
    ng_anterior = prev_indices.get("nivel_general", EMPALME_NIVEL_GENERAL)
    var_ng = variacion_porcentual(ng, ng_anterior)

    # Save to DB
    save_monthly_index(mes, "nivel_general", ng, var_ng, es_oficial=False)

    for div_code, indice in resultado["indices_division"].items():
        var = variaciones.get(div_code)
        if var is not None:
            save_monthly_index(mes, div_code, indice, var, es_oficial=False)

    n_precios = get_price_count_by_month(mes)
    n_dias = get_collection_days_in_month(mes)

    summary = {
        "mes": mes,
        "status": "closed",
        "nivel_general": round(ng, 2),
        "variacion_mensual": round(var_ng, 2),
        "divisiones_con_datos": len(variaciones),
        "n_precios_totales": n_precios,
        "n_dias_recoleccion": n_dias,
    }

    log.info("pipeline.month_closed", **summary)
    return summary


def auto_close_previous_month(fecha: date | None = None):
    """
    If we're in a new month and the previous month hasn't been closed, close it.
    Called at the start of each pipeline run.
    """
    fecha = fecha or date.today()

    # Only auto-close if we're in the first 3 days of a new month
    if fecha.day > 3:
        return

    mes_anterior = _previous_month(fecha.strftime("%Y-%m"))

    # Check if previous month has data but no closed index
    n_precios = get_price_count_by_month(mes_anterior)
    if n_precios == 0:
        return  # No data to close

    from storage.repository import get_index_series
    series = get_index_series("nivel_general")
    closed_months = {s["fecha"] for s in series if not s["es_oficial"]}

    if mes_anterior not in closed_months:
        log.info("pipeline.auto_closing_previous_month", mes=mes_anterior)
        close_month(mes_anterior)


# ─── Helper functions ─────────────────────────────────────────────────────────

def _collect_and_save(fecha: date, collectors_ids: list[str] | None = None) -> list[PriceObservation]:
    """Run collectors, save results to DB, return all observations."""
    all_observations = []

    if collectors_ids:
        collector_list = [get_collector(cid) for cid in collectors_ids]
    else:
        collector_list = get_all_collectors()

    for collector in collector_list:
        start = datetime.utcnow()
        try:
            obs = collector.run()
            elapsed = (datetime.utcnow() - start).total_seconds()

            # Save to DB
            if obs:
                save_raw_prices(obs, collector.collector_id, fecha)

            save_collector_status(
                collector.collector_id, exito=bool(obs),
                n_precios=len(obs), duracion_seg=elapsed,
            )

            all_observations.extend(obs)

        except Exception as e:
            elapsed = (datetime.utcnow() - start).total_seconds()
            log.error("pipeline.collector_error",
                      collector=collector.collector_id, error=str(e))
            save_collector_status(
                collector.collector_id, exito=False,
                n_precios=0, duracion_seg=elapsed, error_msg=str(e),
            )

    return all_observations


def _compute_averages_in_memory(observations: list[PriceObservation]) -> dict[str, float]:
    """Fallback: compute geometric means from in-memory observations."""
    by_division = defaultdict(list)
    for obs in observations:
        if obs.division_coicop and obs.precio > 0:
            by_division[obs.division_coicop].append(obs.precio)

    result = {}
    for div, precios in by_division.items():
        if precios:
            result[div] = float(np.exp(np.mean(np.log(precios))))
    return result


def _previous_month(mes: str) -> str:
    """Get previous month string. '2026-03' → '2026-02'."""
    year, month = int(mes[:4]), int(mes[5:7])
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def _build_fallback_result(fecha: date, mes: str) -> dict:
    """Build a result dict when no observations were collected."""
    return {
        "fecha": str(fecha),
        "mes": mes,
        "error": "No se obtuvieron precios",
        "nivel_general": EMPALME_NIVEL_GENERAL,
        "variacion_periodo": 0.0,
        "n_precios_recolectados": 0,
        "es_oficial": False,
        "fuente": "R&V IPC (sin datos — fallback empalme)",
    }


# ─── Intra-month variation ────────────────────────────────────────────────────

def calcular_variacion_intrames(mes: str | None = None) -> dict:
    """
    Calculate intra-month price variation using MATCHED PRODUCTS.

    Compares only products that appear on both the first and last day
    of the month. This avoids artificial variation from different
    product mixes between days.
    """
    if mes is None:
        mes = date.today().strftime("%Y-%m")

    try:
        ensure_tables()
    except Exception:
        pass

    from storage.repository import (
        get_matched_product_variations, get_matched_daily_series,
    )

    primer_dia = get_first_day_of_month_with_data(mes)
    ultimo_dia = get_last_day_of_month_with_data(mes)

    if not primer_dia or not ultimo_dia:
        return {
            "mes": mes,
            "error": "Sin datos para este mes",
            "n_dias": 0,
        }

    if primer_dia == ultimo_dia:
        return {
            "mes": mes,
            "fecha_inicio": str(primer_dia),
            "fecha_fin": str(ultimo_dia),
            "n_dias": 1,
            "variacion_acumulada_mes": 0.0,
            "mensaje": "Solo 1 día con datos — se necesitan al menos 2 días para calcular variación",
            "variaciones_por_division": {},
            "serie_diaria": [],
        }

    # Use matched-product comparison
    variaciones_div = get_matched_product_variations(primer_dia, ultimo_dia)
    pesos = get_all_weights()

    # Weighted aggregate
    if variaciones_div:
        peso_total = sum(pesos.get(k, 0) for k in variaciones_div if k not in EXCLUIDAS)
        if peso_total > 0:
            var_acumulada = sum(
                variaciones_div[k] * (pesos.get(k, 0) / peso_total)
                for k in variaciones_div
                if k not in EXCLUIDAS
            )
        else:
            var_acumulada = 0.0
    else:
        var_acumulada = 0.0

    # Build matched daily series
    serie_diaria = get_matched_daily_series(mes)

    n_dias = get_collection_days_in_month(mes)

    # Division detail
    div_detail = {}
    for div in DIVISIONES:
        cod = div.codigo
        if cod in EXCLUIDAS:
            continue
        var = variaciones_div.get(cod)
        div_detail[cod] = {
            "nombre": div.nombre_corto,
            "peso_ajustado": pesos.get(cod, 0),
            "variacion_acumulada": round(var, 2) if var is not None else None,
            "tiene_datos": var is not None,
        }

    return {
        "mes": mes,
        "fecha_inicio": str(primer_dia),
        "fecha_fin": str(ultimo_dia),
        "n_dias": n_dias,
        "variacion_acumulada_mes": round(var_acumulada, 2),
        "inflacion_anualizada_estimada": round(inflacion_anualizada(var_acumulada), 1),
        "divisiones_con_datos": sum(1 for v in variaciones_div.values()),
        "cobertura_pct": round(sum(pesos.get(k, 0) for k in variaciones_div if k not in EXCLUIDAS), 1),
        "variaciones_por_division": div_detail,
        "serie_diaria": serie_diaria,
    }


# ─── Convenience wrappers ────────────────────────────────────────────────────

def run_weekly_pipeline(fecha: date | None = None) -> dict:
    return run_pipeline(fecha=fecha, periodo_tipo="semanal")

def run_monthly_pipeline(fecha: date | None = None) -> dict:
    return run_pipeline(fecha=fecha, periodo_tipo="mensual")
    
def calcular_nucleo_intrames(mes: str | None = None) -> dict:
    """
    Calcula la inflación núcleo R&V intra-mes.

    Misma metodología que calcular_variacion_intrames() pero excluyendo:
      - Regulados: 04 (Vivienda/tarifas), 07 (Transporte/combustibles)
    """
    if mes is None:
        mes = date.today().strftime("%Y-%m")

    try:
        ensure_tables()
    except Exception:
        pass

    from storage.repository import (
        get_matched_product_variations,
        get_first_day_of_month_with_data,
        get_last_day_of_month_with_data,
    )

    REGULADOS = {"04", "07"}
    EXCLUIDAS_NUCLEO = EXCLUIDAS | REGULADOS

    primer_dia = get_first_day_of_month_with_data(mes)
    ultimo_dia = get_last_day_of_month_with_data(mes)

    if not primer_dia or not ultimo_dia:
        return {
            "mes": mes,
            "error": "Sin datos para este mes",
            "nucleo": None,
            "n_dias": 0,
        }

    if primer_dia == ultimo_dia:
        return {
            "mes": mes,
            "fecha_inicio": str(primer_dia),
            "fecha_fin": str(ultimo_dia),
            "n_dias": 1,
            "nucleo": None,
            "mensaje": "Solo 1 día con datos — se necesitan al menos 2 días",
            "divisiones": {},
        }

    variaciones_div = get_matched_product_variations(primer_dia, ultimo_dia)
    pesos = get_all_weights()

    variaciones_nucleo = {
        k: v for k, v in variaciones_div.items()
        if k not in EXCLUIDAS_NUCLEO and v is not None
    }

    peso_nucleo_total = sum(pesos.get(k, 0) for k in variaciones_nucleo)

    if peso_nucleo_total > 0:
        nucleo = sum(
            variaciones_nucleo[k] * (pesos.get(k, 0) / peso_nucleo_total)
            for k in variaciones_nucleo
        )
    else:
        nucleo = None

    n_dias = get_collection_days_in_month(mes)

    div_detail = {}
    for div in DIVISIONES:
        cod = div.codigo
        if cod in EXCLUIDAS_NUCLEO:
            continue
        var = variaciones_div.get(cod)
        div_detail[cod] = {
            "nombre": div.nombre_corto,
            "peso_ajustado": pesos.get(cod, 0),
            "peso_nucleo": round(pesos.get(cod, 0) / peso_nucleo_total * 100, 4) if peso_nucleo_total > 0 else 0,
            "variacion_acumulada": round(var, 2) if var is not None else None,
            "tiene_datos": var is not None,
        }

    return {
        "mes": mes,
        "fecha_inicio": str(primer_dia),
        "fecha_fin": str(ultimo_dia),
        "n_dias": n_dias,
        "nucleo": round(nucleo, 2) if nucleo is not None else None,
        "inflacion_anualizada_estimada": round(inflacion_anualizada(nucleo), 1) if nucleo is not None else None,
        "divisiones_excluidas_regulados": list(REGULADOS),
        "divisiones_nucleo_con_datos": len(variaciones_nucleo),
        "cobertura_nucleo_pct": round(peso_nucleo_total, 1),
        "divisiones": div_detail,
    }    
