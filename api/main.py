"""R&V IPC — FastAPI application (auto-collecting)."""
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
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory store ─────────────────────────────────────────────────────────
_latest_result = None
_last_run_time: datetime | None = None
_MIN_RUN_INTERVAL = timedelta(hours=4)  # Don't re-run more than once per 4 hours


def _needs_fresh_run() -> bool:
    """Check if we need to run the pipeline."""
    if _latest_result is None:
        return True
    if _last_run_time is None:
        return True
    # Re-run if last run was more than 4 hours ago
    if datetime.utcnow() - _last_run_time > _MIN_RUN_INTERVAL:
        return True
    # Re-run if last result had an error
    if "error" in _latest_result:
        return True
    return False


def _run_pipeline_safe() -> dict:
    """Run the pipeline with error handling. Returns result dict."""
    global _latest_result, _last_run_time
    try:
        # Import here to avoid circular imports and keep startup fast
        import collectors  # noqa: F401 — triggers @register_collector
        from engine.pipeline import run_pipeline

        result = run_pipeline(fecha=date.today(), periodo_tipo="diario")
        _last_run_time = datetime.utcnow()

        # Only update _latest_result if we got actual prices
        if result and result.get("n_precios_recolectados", 0) > 0:
            _latest_result = result
            log.info("pipeline.success",
                     n_precios=result["n_precios_recolectados"],
                     nivel_general=result["nivel_general"])
        else:
            # Pipeline ran but got no prices — store result but mark it
            _latest_result = result
            log.warning("pipeline.no_prices", result_keys=list(result.keys()))

        return result

    except Exception as e:
        log.error("pipeline.exception", error=str(e))
        _last_run_time = datetime.utcnow()  # Don't retry immediately
        return {"error": str(e), "fecha": str(date.today())}


def _get_empalme_fallback() -> dict:
    """Return empalme data as fallback when pipeline hasn't run."""
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
        "cobertura_pct": 88.5,
        "n_precios_recolectados": 0,
        "divisiones_con_datos": 0,
        "es_oficial": True,
        "fuente": "INDEC (empalme — pipeline no ejecutado aún)",
    }


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "name": "R&V IPC",
        "description": "Proxy de inflación semanal — Argentina",
        "empalme": "IPC-INDEC feb 2026 = 10.714,63",
        "version": "0.3.0",
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
    """
    Returns the latest R&V IPC index.
    Auto-runs the pipeline if no fresh data is available.
    """
    # If we need fresh data, run the pipeline
    if _needs_fresh_run():
        result = _run_pipeline_safe()
        # If pipeline succeeded with prices, return it
        if result.get("n_precios_recolectados", 0) > 0:
            return result

    # Return cached result if available
    if _latest_result and _latest_result.get("n_precios_recolectados", 0) > 0:
        return _latest_result

    # Fallback to empalme data
    return _get_empalme_fallback()


@app.post("/api/v1/index/run")
def trigger_pipeline(
    periodo: str = Query("diario", enum=["diario", "semanal", "mensual"]),
):
    """Force-run collectors and calculate index. Called by daily cron job."""
    global _latest_result, _last_run_time

    try:
        import collectors  # noqa: F401
        from engine.pipeline import run_pipeline

        result = run_pipeline(fecha=date.today(), periodo_tipo=periodo)
        _latest_result = result
        _last_run_time = datetime.utcnow()
        return result

    except Exception as e:
        log.error("pipeline.manual_trigger_error", error=str(e))
        return {"error": str(e), "periodo": periodo}


@app.get("/api/v1/index/divisiones")
def get_divisiones():
    # If we have fresh pipeline data, use it
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

    # Fallback to empalme
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
            "status": "Collectors auto-run on first request + daily cron",
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
    """Debug endpoint: run a single collector and see raw results."""
    try:
        import collectors  # noqa: F401
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
