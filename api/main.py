"""R&V IPC — FastAPI application (with persistence + auto month closing)."""
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import date, datetime, timedelta
from config.ipc_oficial import (
    IPC_DIVISIONES_FEB2026, VAR_DIVISIONES_FEB2026,
    EMPALME_NIVEL_GENERAL,
)
from config.canasta import DIVISIONES, get_all_weights
import structlog

log = structlog.get_logger()

app = FastAPI(
    title="R&V IPC — Proxy de Inflación Argentina",
    description="Índice de precios al consumidor proxy con frecuencia semanal.",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory cache ─────────────────────────────────────────────────────────
_latest_result = None
_last_run_time: datetime | None = None
_MIN_RUN_INTERVAL = timedelta(hours=4)


def _needs_fresh_run() -> bool:
    if _latest_result is None:
        return True
    if _last_run_time is None:
        return True
    if datetime.utcnow() - _last_run_time > _MIN_RUN_INTERVAL:
        return True
    if "error" in _latest_result:
        return True
    return False


def _run_pipeline_safe() -> dict:
    global _latest_result, _last_run_time
    try:
        from engine.pipeline import run_pipeline, auto_close_previous_month

        # Auto-close previous month if needed (e.g. it's April 1, close March)
        auto_close_previous_month()

        result = run_pipeline(fecha=date.today(), periodo_tipo="diario")
        _last_run_time = datetime.utcnow()

        if result and result.get("n_precios_recolectados", 0) > 0:
            _latest_result = result
        else:
            _latest_result = result

        return result

    except Exception as e:
        log.error("pipeline.exception", error=str(e))
        _last_run_time = datetime.utcnow()
        return {"error": str(e), "fecha": str(date.today())}


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "name": "R&V IPC",
        "description": "Proxy de inflación semanal — Argentina",
        "empalme": "IPC-INDEC feb 2026 = 10.714,63",
        "version": "0.4.0",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "latest_run": _last_run_time.isoformat() if _last_run_time else None,
        "has_data": _latest_result is not None and "error" not in (_latest_result or {}),
    }


@app.get("/api/v1/index/nivel-general")
def get_nivel_general():
    """Returns latest R&V IPC index. Auto-runs pipeline if no fresh data."""
    if _needs_fresh_run():
        result = _run_pipeline_safe()
        if result.get("n_precios_recolectados", 0) > 0:
            return result

    if _latest_result and _latest_result.get("n_precios_recolectados", 0) > 0:
        return _latest_result

    # Fallback
    pesos = get_all_weights()
    ng = sum(
        IPC_DIVISIONES_FEB2026.get(cod, 0) * (pesos.get(cod, 0) / 100)
        for cod in pesos
    )
    return {
        "fecha": "2026-02-01",
        "nivel_general": round(ng, 2),
        "variacion_periodo": 2.9,
        "inflacion_anualizada": 40.7,
        "n_precios_recolectados": 0,
        "es_oficial": True,
        "fuente": "INDEC (empalme — pipeline no ejecutado aún)",
    }


@app.post("/api/v1/index/run")
def trigger_pipeline(
    periodo: str = Query("diario", enum=["diario", "semanal", "mensual"]),
):
    """Force-run collectors and calculate index."""
    global _latest_result, _last_run_time
    try:
        from engine.pipeline import run_pipeline, auto_close_previous_month
        auto_close_previous_month()
        result = run_pipeline(fecha=date.today(), periodo_tipo=periodo)
        _latest_result = result
        _last_run_time = datetime.utcnow()
        return result
    except Exception as e:
        log.error("pipeline.trigger_error", error=str(e))
        return {"error": str(e), "periodo": periodo}


@app.post("/api/v1/index/close-month")
def close_month_endpoint(
    mes: str = Query(..., description="Month to close, format YYYY-MM (e.g. 2026-03)"),
):
    """Manually close a month and compute final indices."""
    try:
        from engine.pipeline import close_month
        result = close_month(mes)
        return result
    except Exception as e:
        return {"error": str(e), "mes": mes}


@app.get("/api/v1/index/serie")
def get_serie(
    nivel: str = Query("nivel_general", description="nivel_general or division code (01, 02, etc.)"),
):
    """
    Get full time series: INDEC official + R&V proxy.
    Returns monthly data from jan 2017 onwards.
    """
    try:
        from storage.repository import get_index_series, ensure_tables, seed_empalme_data
        ensure_tables()
        seed_empalme_data()

        # Get R&V series from DB
        rv_series = get_index_series(nivel)

        # Build combined series: INDEC historical + R&V proxy
        # The dashboard already has INDEC data hardcoded (110 months)
        # Here we just return the R&V extension
        return {
            "nivel": nivel,
            "empalme_fecha": "2026-02",
            "empalme_valor": EMPALME_NIVEL_GENERAL if nivel == "nivel_general" else IPC_DIVISIONES_FEB2026.get(nivel),
            "serie_rv": rv_series,
            "n_meses_rv": len([s for s in rv_series if not s["es_oficial"]]),
        }
    except Exception as e:
        return {"error": str(e), "nivel": nivel}


@app.get("/api/v1/index/month-status")
def get_month_status(
    mes: str = Query(None, description="Month YYYY-MM (default: current)"),
):
    """Get collection status for a specific month."""
    try:
        from storage.repository import (
            get_price_count_by_month, get_collection_days_in_month,
            get_monthly_avg_by_division, ensure_tables,
        )
        ensure_tables()

        if not mes:
            mes = date.today().strftime("%Y-%m")

        n_precios = get_price_count_by_month(mes)
        n_dias = get_collection_days_in_month(mes)
        avgs = get_monthly_avg_by_division(mes)

        return {
            "mes": mes,
            "n_precios_totales": n_precios,
            "n_dias_recoleccion": n_dias,
            "divisiones_con_datos": len(avgs),
            "promedios_por_division": {
                k: round(v, 2) for k, v in avgs.items()
            },
        }
    except Exception as e:
        return {"error": str(e), "mes": mes}


@app.get("/api/v1/index/intrames")
def get_intra_month(
    mes: str = Query(None, description="Month YYYY-MM (default: current)"),
):
    """
    Intra-month price variation: how prices evolved within the current month.

    Compares prices on the latest day vs the first day of the month.
    Returns accumulated variation by division + daily time series.

    This is the real-time inflation signal — usable from day 2 of each month.
    """
    try:
        from engine.pipeline import calcular_variacion_intrames
        if not mes:
            mes = date.today().strftime("%Y-%m")
        return calcular_variacion_intrames(mes)
    except Exception as e:
        return {"error": str(e), "mes": mes}

@app.get("/api/v1/index/intrames/nucleo")
def get_intra_month_nucleo(
    mes: str = Query(None, description="Month YYYY-MM (default: current)"),
):
    """
    Inflación núcleo R&V intra-mes.

    Misma metodología que /intrames pero excluyendo divisiones reguladas
    (04 Vivienda/tarifas, 07 Transporte/combustibles).

    Comparable con la categoría Núcleo del INDEC.
    """
    try:
        from engine.pipeline import calcular_nucleo_intrames
        if not mes:
            mes = date.today().strftime("%Y-%m")
        return calcular_nucleo_intrames(mes)
    except Exception as e:
        return {"error": str(e), "mes": mes}

@app.get("/api/v1/index/divisiones")
def get_divisiones():
    if _latest_result and "divisiones" in _latest_result:
        divs = _latest_result["divisiones"]
        return {
            "fecha": _latest_result.get("fecha", str(date.today())),
            "fuente": "R&V IPC (pipeline)",
            "divisiones": [
                {
                    "codigo": div.codigo,
                    "nombre": div.nombre,
                    "nombre_corto": div.nombre_corto,
                    "peso_gba": div.peso_gba,
                    "indice": divs.get(div.codigo, {}).get("indice") if isinstance(divs.get(div.codigo), dict) else IPC_DIVISIONES_FEB2026.get(div.codigo),
                    "var_mensual": divs.get(div.codigo, {}).get("variacion") if isinstance(divs.get(div.codigo), dict) else VAR_DIVISIONES_FEB2026.get(div.codigo),
                    "tiene_datos": divs.get(div.codigo, {}).get("tiene_datos", False) if isinstance(divs.get(div.codigo), dict) else False,
                    "tiene_collector": bool(div.collector_ids),
                }
                for div in DIVISIONES
            ],
        }

    return {
        "fecha": "2026-02-01",
        "fuente": "INDEC (empalme)",
        "divisiones": [
            {
                "codigo": div.codigo,
                "nombre": div.nombre,
                "nombre_corto": div.nombre_corto,
                "peso_gba": div.peso_gba,
                "indice": IPC_DIVISIONES_FEB2026.get(div.codigo),
                "var_mensual": VAR_DIVISIONES_FEB2026.get(div.codigo),
                "tiene_datos": False,
                "tiene_collector": bool(div.collector_ids),
            }
            for div in DIVISIONES
        ],
    }

@app.post("/api/v1/admin/backfill-base-day")
def backfill_base_day(
    mes: str = Query(None, description="Month YYYY-MM (default: current)"),
    dry_run: bool = Query(True, description="If True, only shows what would be inserted without saving"),
):
    """
    Fix divisions that are missing data on the first day of the month.
 
    The matched-product comparison requires each division to have prices on
    BOTH the base day (first day with data) AND the comparison day (latest).
    If a collector only started working mid-month, it has no base day data
    and shows null variation.
 
    This endpoint takes the EARLIEST available prices for each missing division
    and copies them to the base day, giving the system a valid starting point.
 
    Safe to run multiple times (idempotent — skips divisions that already
    have data on the base day).
    """
    try:
        from storage.repository import (
            ensure_tables, get_first_day_of_month_with_data,
            save_raw_prices,
        )
        from storage.models import PrecioRaw
        from collectors.base import PriceObservation
        from sqlalchemy import func, distinct
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import create_engine
        from config.settings import get_settings
 
        ensure_tables()
 
        if not mes:
            mes = date.today().strftime("%Y-%m")
 
        year, month = int(mes[:4]), int(mes[5:7])
        if month == 12:
            fecha_fin = date(year + 1, 1, 1)
        else:
            fecha_fin = date(year, month + 1, 1)
        fecha_inicio = date(year, month, 1)
 
        # Get base day (first day with ANY data this month)
        base_day = get_first_day_of_month_with_data(mes)
        if not base_day:
            return {"error": f"No hay datos para {mes}"}
 
        s = get_settings()
        engine = create_engine(s.DATABASE_URL_SYNC, pool_pre_ping=True)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
 
        try:
            # Find which divisions already have data on base_day
            divs_on_base = session.query(
                distinct(PrecioRaw.division_coicop)
            ).filter(
                PrecioRaw.fecha == base_day,
                PrecioRaw.division_coicop.isnot(None),
                PrecioRaw.division_coicop != "",
            ).all()
            divs_on_base = {d[0] for d in divs_on_base}
 
            # Find all divisions that have data this month
            divs_this_month = session.query(
                distinct(PrecioRaw.division_coicop)
            ).filter(
                PrecioRaw.fecha >= fecha_inicio,
                PrecioRaw.fecha < fecha_fin,
                PrecioRaw.division_coicop.isnot(None),
                PrecioRaw.division_coicop != "",
            ).all()
            divs_this_month = {d[0] for d in divs_this_month}
 
            # Divisions that need backfill
            divs_missing = divs_this_month - divs_on_base
 
            if not divs_missing:
                return {
                    "mes": mes,
                    "base_day": str(base_day),
                    "status": "ok — todas las divisiones ya tienen datos en el día base",
                    "divisiones_con_base": sorted(divs_on_base),
                }
 
            results = []
 
            for div in sorted(divs_missing):
                # Find the earliest day this division has data
                earliest_date = session.query(
                    func.min(PrecioRaw.fecha)
                ).filter(
                    PrecioRaw.fecha >= fecha_inicio,
                    PrecioRaw.fecha < fecha_fin,
                    PrecioRaw.division_coicop == div,
                ).scalar()
 
                if not earliest_date:
                    continue
 
                # Get all prices from that earliest day for this division
                rows = session.query(PrecioRaw).filter(
                    PrecioRaw.fecha == earliest_date,
                    PrecioRaw.division_coicop == div,
                ).all()
 
                if not rows:
                    continue
 
                result_entry = {
                    "division": div,
                    "earliest_date": str(earliest_date),
                    "n_precios": len(rows),
                    "productos": [r.producto for r in rows[:5]],
                }
 
                if not dry_run:
                    # Build PriceObservation objects with base_day as fecha
                    observations = []
                    for row in rows:
                        observations.append(PriceObservation(
                            producto=row.producto,
                            precio=row.precio,
                            unidad=row.unidad,
                            categoria_coicop=row.categoria_coicop or "",
                            division_coicop=row.division_coicop,
                            fuente=f"{row.fuente} [backfill desde {earliest_date}]",
                            url=row.url or "",
                        ))
 
                    saved = save_raw_prices(observations, row.collector_id, base_day)
                    result_entry["saved"] = saved
                    result_entry["status"] = "backfilled"
                else:
                    result_entry["status"] = "dry_run — no se guardó nada"
 
                results.append(result_entry)
 
        finally:
            session.close()
 
        return {
            "mes": mes,
            "base_day": str(base_day),
            "dry_run": dry_run,
            "divisiones_ya_con_base": sorted(divs_on_base),
            "divisiones_backfilleadas": results,
            "nota": "Corré con dry_run=false para aplicar los cambios" if dry_run else "Cambios aplicados. Ahora corré POST /api/v1/index/run para recalcular.",
        }
 
    except Exception as e:
        log.error("backfill.error", error=str(e))
        return {"error": str(e)}

@app.post("/api/v1/admin/replace-base-day-division")
def replace_base_day_division(
    division: str = Query(..., description="Division code, e.g. '06'"),
    mes: str = Query(None, description="Month YYYY-MM (default: current)"),
    dry_run: bool = Query(True, description="If True, only shows what would happen"),
):
    """
    Replace prices for a specific division on the base day with
    the most recent day's prices for that division.
    """
    try:
        from storage.repository import (
            ensure_tables, get_first_day_of_month_with_data, save_raw_prices,
        )
        from storage.models import PrecioRaw
        from collectors.base import PriceObservation
        from sqlalchemy import func, distinct
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import create_engine
        from config.settings import get_settings
 
        ensure_tables()
 
        if not mes:
            mes = date.today().strftime("%Y-%m")
 
        year, month = int(mes[:4]), int(mes[5:7])
        if month == 12:
            fecha_fin = date(year + 1, 1, 1)
        else:
            fecha_fin = date(year, month + 1, 1)
        fecha_inicio = date(year, month, 1)
 
        base_day = get_first_day_of_month_with_data(mes)
        if not base_day:
            return {"error": f"No hay datos para {mes}"}
 
        s = get_settings()
        engine = create_engine(s.DATABASE_URL_SYNC, pool_pre_ping=True)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
 
        try:
            # Get current prices on base_day for this division
            existing = session.query(PrecioRaw).filter(
                PrecioRaw.fecha == base_day,
                PrecioRaw.division_coicop == division,
            ).all()
            existing_count = len(existing)
            existing_productos = [r.producto for r in existing[:5]]
 
            # Get most recent day's prices for this division
            latest_date = session.query(func.max(PrecioRaw.fecha)).filter(
                PrecioRaw.fecha >= fecha_inicio,
                PrecioRaw.fecha < fecha_fin,
                PrecioRaw.division_coicop == division,
                PrecioRaw.fecha != base_day,
            ).scalar()
 
            if not latest_date:
                return {"error": f"No hay precios recientes para división {division}"}
 
            latest_rows = session.query(PrecioRaw).filter(
                PrecioRaw.fecha == latest_date,
                PrecioRaw.division_coicop == division,
            ).all()
 
            # Read all data while session is open
            observations = []
            collector_id = f"{division}_backfill"
            for row in latest_rows:
                collector_id = row.collector_id  # use real collector_id
                observations.append(PriceObservation(
                    producto=row.producto,
                    precio=row.precio,
                    unidad=row.unidad,
                    categoria_coicop=row.categoria_coicop or "",
                    division_coicop=row.division_coicop,
                    fuente=f"{row.fuente} [reemplazado desde {latest_date}]",
                    url=row.url or "",
                ))
 
            if dry_run:
                return {
                    "division": division,
                    "base_day": str(base_day),
                    "latest_date": str(latest_date),
                    "precios_a_eliminar": existing_count,
                    "productos_actuales": existing_productos,
                    "precios_a_insertar": len(observations),
                    "productos_nuevos": [o.producto for o in observations[:5]],
                    "dry_run": True,
                    "nota": "Corré con dry_run=false para aplicar",
                }
 
            # Delete existing base day prices for this division
            session.query(PrecioRaw).filter(
                PrecioRaw.fecha == base_day,
                PrecioRaw.division_coicop == division,
            ).delete()
            session.commit()
 
        finally:
            session.close()
 
        # Insert latest prices with base_day date (session already closed)
        saved = save_raw_prices(observations, collector_id, base_day)
 
        return {
            "division": division,
            "base_day": str(base_day),
            "latest_date": str(latest_date),
            "eliminados": existing_count,
            "insertados": saved,
            "status": "ok — reemplazado",
            "nota": "Ahora corré POST /api/v1/index/run para recalcular.",
        }
 
    except Exception as e:
        log.error("replace_base_day.error", error=str(e))
        return {"error": str(e)}
        
@app.get("/api/v1/index/cobertura")
def get_cobertura():
    cubiertas = [d for d in DIVISIONES if d.collector_ids]
    no_cubiertas = [d for d in DIVISIONES if not d.collector_ids]
    return {
        "total_divisiones": 12,
        "cubiertas": len(cubiertas),
        "peso_cubierto_pct": round(sum(d.peso_gba for d in cubiertas), 1),
        "divisiones_cubiertas": [
            {"codigo": d.codigo, "nombre": d.nombre_corto, "peso": d.peso_gba,
             "collectors": d.collector_ids}
            for d in cubiertas
        ],
        "divisiones_sin_cubrir": [
            {"codigo": d.codigo, "nombre": d.nombre_corto, "peso": d.peso_gba}
            for d in no_cubiertas
        ],
    }


@app.get("/api/v1/status/collectors")
def get_status():
    try:
        from collectors.registry import list_collectors, get_collector
        collectors_list = list_collectors()
        return {
            "total": len(collectors_list),
            "last_run": _last_run_time.isoformat() if _last_run_time else None,
            "collectors": [
                {
                    "id": cid,
                    "description": get_collector(cid).description,
                    "division": get_collector(cid).division_coicop,
                }
                for cid in collectors_list
            ],
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/v1/debug/run-single")
def debug_run_single(
    collector_id: str = Query(..., description="Collector ID to test"),
):
    """Debug: run a single collector and see raw results."""
    try:
        import collectors as _c  # noqa: F401
        from collectors.registry import get_collector
        collector = get_collector(collector_id)
        observations = collector.run()
        return {
            "collector": collector_id,
            "fecha": str(date.today()),
            "n_precios": len(observations),
            "precios": [
                {
                    "producto": o.producto,
                    "precio": o.precio,
                    "unidad": o.unidad,
                    "division": o.division_coicop,
                    "categoria": o.categoria_coicop,
                    "fuente": o.fuente,
                }
                for o in observations
            ],
        }
    except KeyError:
        from collectors.registry import list_collectors
        return {"error": f"Collector '{collector_id}' not found",
                "available": list_collectors()}
    except Exception as e:
        return {"error": str(e), "collector": collector_id}
# Agregar en api/main.py antes del footer/último endpoint

# Reemplazar el endpoint /api/v1/debug/matched-products en main.py

@app.get("/api/v1/debug/matched-products")
def debug_matched_products(
    division: str = Query(..., description="Division code, e.g. '06'"),
    mes: str = Query(None, description="Month YYYY-MM (default: current)"),
):
    """
    Show matched products for a division between base day and latest day.
    Useful for diagnosing unexpected variation in a division.
    """
    try:
        from storage.repository import (
            ensure_tables,
            get_first_day_of_month_with_data,
            get_last_day_of_month_with_data,
        )
        from storage.models import PrecioRaw
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import create_engine
        from config.settings import get_settings
        import numpy as np
        from collections import defaultdict

        ensure_tables()

        if not mes:
            mes = date.today().strftime("%Y-%m")

        base_day = get_first_day_of_month_with_data(mes)
        latest_day = get_last_day_of_month_with_data(mes)

        if not base_day or not latest_day:
            return {"error": f"Sin datos para {mes}"}

        if base_day == latest_day:
            return {"error": "Solo hay un día con datos, se necesitan al menos 2"}

        s = get_settings()
        engine = create_engine(s.DATABASE_URL_SYNC, pool_pre_ping=True)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        try:
            rows = session.query(PrecioRaw).filter(
                PrecioRaw.fecha.in_([base_day, latest_day]),
                PrecioRaw.division_coicop == division,
                PrecioRaw.precio > 0,
            ).all()

            # Agrupar precios por (fecha, producto) — puede haber múltiples observaciones
            grupos_base = defaultdict(list)
            grupos_latest = defaultdict(list)
            meta = {}  # nombre original y fuente por key

            for row in rows:
                key = row.producto.strip().lower()
                meta[key] = {"nombre": row.producto, "fuente": row.fuente}
                if row.fecha == base_day:
                    grupos_base[key].append(row.precio)
                else:
                    grupos_latest[key].append(row.precio)

        finally:
            session.close()

        # Promedio por producto en cada día
        prices_base = {k: float(np.mean(v)) for k, v in grupos_base.items()}
        prices_latest = {k: float(np.mean(v)) for k, v in grupos_latest.items()}

        # Matched keys
        matched_keys = set(prices_base.keys()) & set(prices_latest.keys())
        unmatched_base = set(prices_base.keys()) - matched_keys
        unmatched_latest = set(prices_latest.keys()) - matched_keys

        # Variación por producto
        productos_matched = []
        relatives = []

        for key in matched_keys:
            p_base = prices_base[key]
            p_latest = prices_latest[key]
            relative = p_latest / p_base
            relatives.append(relative)
            var_pct = (relative - 1) * 100

            productos_matched.append({
                "producto": meta[key]["nombre"],
                "precio_base": round(p_base, 2),
                "precio_actual": round(p_latest, 2),
                "variacion_pct": round(var_pct, 2),
                "fuente": meta[key]["fuente"],
            })

        # Ordenar de mayor a menor variación
        productos_matched.sort(key=lambda x: x["variacion_pct"], reverse=True)

        # Media geométrica de la división
        if relatives:
            geo_mean = float(np.exp(np.mean(np.log(relatives))))
            var_division = round((geo_mean - 1) * 100, 3)
        else:
            var_division = None

        return {
            "division": division,
            "mes": mes,
            "base_day": str(base_day),
            "latest_day": str(latest_day),
            "variacion_division_pct": var_division,
            "n_matched": len(matched_keys),
            "n_solo_en_base": len(unmatched_base),
            "n_solo_en_actual": len(unmatched_latest),
            "productos_no_matcheados_base": [
                meta[k]["nombre"] for k in list(unmatched_base)[:10]
            ],
            "productos_no_matcheados_actual": [
                meta[k]["nombre"] for k in list(unmatched_latest)[:10]
            ],
            "productos_matched": productos_matched,
        }

    except Exception as e:
        log.error("debug_matched.error", error=str(e))
        return {"error": str(e)}

@app.post("/api/v1/prices/ingest-external")
def ingest_external_prices(payload: dict):
    """
    Receive prices from external sources (e.g. GitHub Actions Playwright job).
    Saves them to DB as raw prices.
    """
    try:
        from storage.repository import ensure_tables, save_raw_prices
        from collectors.base import PriceObservation

        ensure_tables()

        fecha_str = payload.get("fecha", str(date.today()))
        fecha_parsed = date.fromisoformat(fecha_str)
        source = payload.get("source", "external")
        collectors_data = payload.get("collectors", [])

        total_saved = 0
        results = []

        for coll in collectors_data:
            cid = coll.get("collector_id", "unknown")
            precios = coll.get("precios", [])

            if not precios:
                results.append({"collector": cid, "saved": 0})
                continue

            # Convert to PriceObservation objects
            observations = []
            for p in precios:
                try:
                    observations.append(PriceObservation(
                        producto=p.get("producto", ""),
                        precio=float(p.get("precio", 0)),
                        unidad=p.get("unidad", "unidad"),
                        categoria_coicop=p.get("categoria_coicop", ""),
                        division_coicop=p.get("division_coicop", ""),
                        fuente=p.get("fuente", source),
                    ))
                except Exception:
                    continue

            n_saved = save_raw_prices(observations, cid, fecha_parsed)
            total_saved += n_saved
            results.append({"collector": cid, "received": len(precios), "saved": n_saved})

        return {
            "status": "ok",
            "fecha": fecha_str,
            "source": source,
            "total_saved": total_saved,
            "collectors": results,
        }

    except Exception as e:
        log.error("ingest.error", error=str(e))
        return {"error": str(e)}
