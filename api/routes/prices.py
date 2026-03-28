"""R&V IPC — Price API routes."""
from fastapi import APIRouter, Query
from datetime import date
from collectors.registry import list_collectors, get_collector

router = APIRouter()


@router.get("/latest")
async def get_latest_prices(
    division: str | None = Query(None, description="COICOP division code"),
    collector: str | None = Query(None, description="Collector ID"),
    limit: int = Query(50, ge=1, le=500),
):
    """Get latest collected prices."""
    return {
        "fecha": str(date.today()),
        "message": "Connect to DB for historical prices",
        "filters": {"division": division, "collector": collector},
    }


@router.get("/collect-now")
async def collect_now(
    collector_id: str = Query(..., description="Collector ID to run"),
):
    """Run a specific collector and return results."""
    try:
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
                for o in observations[:20]
            ],
        }
    except KeyError:
        return {"error": f"Collector '{collector_id}' not found",
                "available": list_collectors()}
    except Exception as e:
        return {"error": str(e), "collector": collector_id}
