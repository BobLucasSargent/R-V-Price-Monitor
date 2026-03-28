"""R&V IPC — Index API routes."""
from fastapi import APIRouter, Query
from datetime import date
from engine.pipeline import run_pipeline, run_weekly_pipeline
from config.ipc_oficial import (
    IPC_OFICIAL, IPC_DIVISIONES_FEB2026, VAR_DIVISIONES_FEB2026,
    EMPALME_NIVEL_GENERAL,
)
from config.canasta import DIVISIONES, covered_weight, total_weight

router = APIRouter()


@router.get("/nivel-general")
async def get_nivel_general():
    """Latest R&V IPC nivel general."""
    # For now, return empalme + run pipeline
    try:
        result = run_pipeline(periodo_tipo="diario")
        return result
    except Exception as e:
        # Fallback to empalme data
        return {
            "fecha": "2026-02-01",
            "nivel_general": EMPALME_NIVEL_GENERAL,
            "variacion_periodo": 2.9,
            "es_oficial": True,
            "source": "INDEC (empalme)",
            "error": str(e),
        }


@router.get("/divisiones")
async def get_divisiones():
    """Current index by COICOP division."""
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
                "tiene_collector": bool(div.collector_ids),
            }
            for div in DIVISIONES
        ],
    }


@router.get("/cobertura")
async def get_cobertura():
    """Coverage stats."""
    cubiertas = [d for d in DIVISIONES if d.collector_ids]
    no_cubiertas = [d for d in DIVISIONES if not d.collector_ids]

    return {
        "total_divisiones": 12,
        "cubiertas": len(cubiertas),
        "peso_cubierto_pct": round(covered_weight(), 1),
        "peso_total_pct": round(total_weight(), 1),
        "divisiones_cubiertas": [
            {"codigo": d.codigo, "nombre": d.nombre_corto, "peso": d.peso_gba,
             "collectors": d.collector_ids}
            for d in cubiertas
        ],
        "divisiones_sin_cubrir": [
            {"codigo": d.codigo, "nombre": d.nombre_corto, "peso": d.peso_gba,
             "razon": "Sin fuente online confiable"}
            for d in no_cubiertas
        ],
    }


@router.get("/serie-oficial")
async def get_serie_oficial():
    """Official INDEC data used for empalme."""
    return {
        "base": "dic 2016 = 100",
        "empalme_fecha": "2026-02-01",
        "empalme_nivel_general": EMPALME_NIVEL_GENERAL,
        "ultimos_meses": IPC_OFICIAL,
    }


@router.post("/run")
async def trigger_pipeline(
    periodo: str = Query("diario", enum=["diario", "semanal", "mensual"]),
):
    """Manually trigger index calculation."""
    result = run_pipeline(fecha=date.today(), periodo_tipo=periodo)
    return result
