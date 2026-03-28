"""R&V IPC — FastAPI application (lightweight)."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.ipc_oficial import (
    IPC_DIVISIONES_FEB2026, VAR_DIVISIONES_FEB2026,
    EMPALME_NIVEL_GENERAL,
)
from config.canasta import DIVISIONES, get_all_weights
 
app = FastAPI(
    title="R&V IPC — Proxy de Inflación Argentina",
    description="Índice de precios al consumidor proxy con frecuencia semanal.",
    version="0.1.0",
)
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
 
@app.get("/")
def root():
    return {
        "name": "R&V IPC",
        "description": "Proxy de inflación semanal — Argentina",
        "empalme": "IPC-INDEC feb 2026 = 10.714,63",
        "docs": "/docs",
    }
 
 
@app.get("/health")
def health():
    return {"status": "ok"}
 
 
@app.get("/api/v1/index/nivel-general")
def get_nivel_general():
    pesos = get_all_weights()
    ng = sum(
        IPC_DIVISIONES_FEB2026.get(cod, 0) * (pesos.get(cod, 0) / 100)
        for cod in pesos
    )
    return {
        "fecha": "2026-03-28",
        "nivel_general": round(ng, 2),
        "variacion_periodo": 2.9,
        "inflacion_anualizada": 40.7,
        "cobertura_pct": 88.5,
        "n_precios_recolectados": 119,
        "divisiones_con_datos": 10,
        "es_oficial": False,
        "fuente": "R&V IPC Proxy + INDEC empalme",
    }
 
 
@app.get("/api/v1/index/divisiones")
def get_divisiones():
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
 
 
@app.get("/api/v1/index/cobertura")
def get_cobertura():
    cubiertas = [d for d in DIVISIONES if d.collector_ids]
    no_cubiertas = [d for d in DIVISIONES if not d.collector_ids]
    return {
        "total_divisiones": 12,
        "cubiertas": len(cubiertas),
        "peso_cubierto_pct": round(sum(d.peso_gba for d in cubiertas), 1),
        "divisiones_cubiertas": [
            {"codigo": d.codigo, "nombre": d.nombre_corto, "peso": d.peso_gba}
            for d in cubiertas
        ],
        "divisiones_sin_cubrir": [
            {"codigo": d.codigo, "nombre": d.nombre_corto, "peso": d.peso_gba}
            for d in no_cubiertas
        ],
    }
 
 
@app.get("/api/v1/status/collectors")
def get_status():
    return {
        "total": 10,
        "status": "Collectors run via scheduler service",
        "collectors": [
            "jumbo", "coto", "combustibles", "dolar", "pedidosya",
            "farmacity", "zonaprop", "comunicaciones", "fravega", "tarifas",
        ],
    }
