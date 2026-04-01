"""R&V IPC — Status API routes."""
from fastapi import APIRouter
from collectors.registry import list_collectors, get_collector

router = APIRouter()


@router.get("/collectors")
async def get_collectors_status():
    """List all registered collectors."""
    collectors = list_collectors()
    return {
        "total": len(collectors),
        "collectors": [
            {
                "id": cid,
                "description": get_collector(cid).description,
                "division": get_collector(cid).division_coicop,
            }
            for cid in collectors
        ],
    }


@router.get("/health")
async def system_health():
    return {
        "api": "ok",
        "collectors_registered": len(list_collectors()),
    }
