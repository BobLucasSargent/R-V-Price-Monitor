"""R&V IPC — FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import os

from config.settings import get_settings
from api.routes import prices, index, status

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    settings = get_settings()
    log.info("app.startup", app=settings.APP_NAME)

    # Auto-create database tables
    try:
        db_url = os.environ.get("DATABASE_URL_SYNC", settings.DATABASE_URL_SYNC)
        from storage.models import create_tables
        create_tables(db_url)
        log.info("app.tables_created")
    except Exception as e:
        log.warning("app.tables_error", error=str(e))

    # Import all collectors to trigger registration
    import collectors.supermercados.jumbo
    import collectors.supermercados.coto
    import collectors.combustibles.combustibles
    import collectors.financieros.dolar
    import collectors.delivery.pedidosya
    import collectors.medicamentos.farmacity
    import collectors.alquileres.zonaprop
    import collectors.comunicacion.planes
    import collectors.electronica.fravega
    import collectors.tarifas.servicios

    from collectors.registry import list_collectors
    log.info("collectors.registered", collectors=list_collectors())

    yield

    log.info("app.shutdown")


app = FastAPI(
    title="R&V IPC — Proxy de Inflación Argentina",
    description=(
        "Índice de precios al consumidor proxy con frecuencia semanal. "
        "Empalme con IPC-INDEC base dic 2016=100. "
        "Metodología: Laspeyres, media geométrica, ponderadores GBA."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow React dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
app.include_router(index.router, prefix="/api/v1/index", tags=["Índice"])
app.include_router(prices.router, prefix="/api/v1/prices", tags=["Precios"])
app.include_router(status.router, prefix="/api/v1/status", tags=["Status"])


@app.get("/")
async def root():
    return {
        "name": "R&V IPC",
        "description": "Proxy de inflación semanal — Argentina",
        "empalme": "IPC-INDEC feb 2026 = 10.714,63",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
