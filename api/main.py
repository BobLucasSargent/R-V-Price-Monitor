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
                for o in observations[:30]
            ],
        }
    except KeyError:
        from collectors.registry import list_collectors
        return {"error": f"Collector '{collector_id}' not found",
                "available": list_collectors()}
    except Exception as e:
        return {"error": str(e), "collector": collector_id}


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
