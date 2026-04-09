import logging
from fastapi import APIRouter, Request
from database.db import get_db_session
from modules.analytics import get_wallet_stats, get_recent_trades, get_scheduler_health
from dashboard.app import templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def index(request: Request):
    """Dashboard overview."""
    try:
        with get_db_session() as db:
            stats1 = get_wallet_stats("strategy1", db)
            stats2 = get_wallet_stats("strategy2", db)
            recent = get_recent_trades(db, limit=10)
            health = get_scheduler_health(db)

        return templates.TemplateResponse("index.html", {
            "request": request,
            "stats1": stats1,
            "stats2": stats2,
            "recent_trades": recent,
            "health": health,
        })
    except Exception as e:
        logger.error(f"Error rendering index: {e}", exc_info=True)
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": str(e),
            "stats1": {},
            "stats2": {},
            "recent_trades": [],
            "health": {},
        })
