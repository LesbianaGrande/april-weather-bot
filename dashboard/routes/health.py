import logging
import requests
from fastapi import APIRouter, Request
from database.db import get_db_session
from database.models import SchedulerLog
from modules.analytics import get_scheduler_health
from dashboard.app import templates
from scheduler.jobs import is_running
from config.settings import GAMMA_API_BASE, OPENMETEO_BASE
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()


def test_api_connectivity(url: str) -> dict:
    """Test API connectivity."""
    try:
        response = requests.get(url, timeout=5)
        return {
            "status": "ok" if response.status_code < 500 else "error",
            "code": response.status_code,
            "message": "OK" if response.status_code < 500 else "Server Error"
        }
    except requests.Timeout:
        return {"status": "timeout", "code": None, "message": "Request timeout"}
    except Exception as e:
        return {"status": "error", "code": None, "message": str(e)}


@router.get("/health")
async def health_check(request: Request):
    """System health status."""
    try:
        # Check scheduler
        scheduler_running = is_running()

        # Check APIs
        gamma_status = test_api_connectivity(f"{GAMMA_API_BASE}/markets?limit=1")
        openmeteo_status = test_api_connectivity(f"{OPENMETEO_BASE}/forecast?latitude=0&longitude=0&daily=temperature_2m_max")

        # Get health data
        with get_db_session() as db:
            health = get_scheduler_health(db)
            job_history = db.query(SchedulerLog).order_by(SchedulerLog.run_at.desc()).limit(20).all()
            job_history_data = []
            for log in job_history:
                job_history_data.append({
                    "time": log.run_at.isoformat(),
                    "job": log.job_name,
                    "status": log.status,
                    "trades": log.trades_executed,
                    "resolutions": log.resolutions_processed,
                    "duration": f"{log.duration_seconds:.2f}s" if log.duration_seconds else "-"
                })

        return templates.TemplateResponse("health.html", {
            "request": request,
            "scheduler_running": scheduler_running,
            "scheduler_status": "Running" if scheduler_running else "Stopped",
            "gamma_api_status": gamma_status["status"],
            "openmeteo_api_status": openmeteo_status["status"],
            "health": health,
            "job_history": job_history_data,
            "current_time": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.error(f"Error rendering health: {e}", exc_info=True)
        return templates.TemplateResponse("health.html", {
            "request": request,
            "error": str(e),
            "scheduler_running": False,
            "scheduler_status": "Unknown",
            "gamma_api_status": "unknown",
            "openmeteo_api_status": "unknown",
            "health": {},
            "job_history": [],
            "current_time": datetime.utcnow().isoformat(),
        })
