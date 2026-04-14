import logging
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from database.db import get_db_session
from database.models import Wallet
from modules.analytics import get_wallet_stats, get_recent_trades, get_scheduler_health
from dashboard.app import templates
from scheduler import jobs as scheduler_jobs

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_health_context(db) -> dict:
    """Build scheduler health dict with keys matching the template."""
    job_logs = get_scheduler_health(db)
    trade_scan_log = job_logs.get("trade_scan", {})

    is_running = scheduler_jobs.is_running()
    sched = scheduler_jobs.get_scheduler()
    jobs_count = len(sched.get_jobs()) if is_running else 0

    last_scan_raw = trade_scan_log.get("last_run")
    if last_scan_raw:
        try:
            last_scan = datetime.fromisoformat(last_scan_raw).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            last_scan = last_scan_raw
    else:
        last_scan = "Never"

    next_scan = "08:00 / 14:00 / 20:00 UTC" if is_running else "Scheduler stopped"

    return {
        "scheduler_running": is_running,
        "jobs_count": jobs_count,
        "last_scan": last_scan,
        "next_scan": next_scan,
        "last_scan_trades": trade_scan_log.get("trades_executed", 0),
        "last_scan_status": trade_scan_log.get("status", "unknown"),
    }


@router.get("/")
async def index(request: Request):
    """Dashboard overview."""
    try:
        with get_db_session() as db:
            stats1 = get_wallet_stats("strategy1", db)
            stats2 = get_wallet_stats("strategy2", db)
            recent = get_recent_trades(db, limit=20)
            health = _build_health_context(db)

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
            "health": {"scheduler_running": False, "jobs_count": 0,
                       "last_scan": "Error", "next_scan": "Unknown"},
        })


@router.post("/scan")
async def manual_scan(request: Request):
    """Trigger a manual trade scan immediately."""
    import threading
    from scheduler.jobs import run_trade_scan
    thread = threading.Thread(target=run_trade_scan, daemon=True)
    thread.start()
    return JSONResponse({"status": "ok", "message": "Manual scan started in background"})


@router.post("/reset-wallets")
async def reset_wallets(request: Request):
    """Reset both paper trading wallets to starting balance."""
    try:
        from config.settings import STARTING_BALANCE
        with get_db_session() as db:
            wallets = db.query(Wallet).all()
            reset_count = 0
            for wallet in wallets:
                wallet.balance = STARTING_BALANCE
                wallet.updated_at = datetime.utcnow()
                db.add(wallet)
                reset_count += 1
            db.commit()
        logger.info(f"Reset {reset_count} wallets to balance {STARTING_BALANCE}")
        return JSONResponse({
            "status": "ok",
            "message": f"Reset {reset_count} wallet(s) to starting balance"
        })
    except Exception as e:
        logger.error(f"Error resetting wallets: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
