import logging
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from config.settings import TRADE_SCAN_HOURS, RESOLUTION_CHECK_HOURS
from database.db import get_db_session
from database.models import SchedulerLog

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone=pytz.utc)
_strategies = []
_resolution_checker = None


def setup_scheduler(strategies, resolution_checker_instance):
    """Set up scheduled jobs."""
    global _strategies, _resolution_checker
    _strategies = strategies
    _resolution_checker = resolution_checker_instance

    # Parse hours from config
    scan_hours = ",".join(str(int(h.strip())) for h in TRADE_SCAN_HOURS.split(","))
    resolution_hours = ",".join(str(int(h.strip())) for h in RESOLUTION_CHECK_HOURS.split(","))

    # Add jobs
    _scheduler.add_job(
        run_trade_scan,
        CronTrigger(hour=scan_hours, timezone="UTC"),
        id="trade_scan",
        replace_existing=True
    )
    _scheduler.add_job(
        run_resolution_check,
        CronTrigger(hour=resolution_hours, timezone="UTC"),
        id="resolution_check",
        replace_existing=True
    )

    logger.info(f"Scheduler setup: trade_scan at {scan_hours} UTC, resolution_check at {resolution_hours} UTC")


def start():
    """Start the scheduler."""
    _scheduler.start()
    logger.info("Scheduler started")


def stop():
    """Stop the scheduler."""
    _scheduler.shutdown()
    logger.info("Scheduler stopped")


def get_scheduler():
    """Get the scheduler instance."""
    return _scheduler


def run_trade_scan():
    """Execute trade scan for all strategies."""
    logger.info("Starting trade scan job...")
    start_time = time.time()
    total_trades = 0
    status = "success"
    message = ""

    try:
        with get_db_session() as db:
            for strategy in _strategies:
                try:
                    n = strategy.run_scan(db)
                    total_trades += n
                    logger.info(f"Strategy {strategy.NAME}: {n} trades executed")
                except Exception as e:
                    logger.error(f"Strategy {strategy.NAME} error: {e}", exc_info=True)
                    message += f"{strategy.NAME}: {str(e)}; "
                    status = "partial_error" if status == "success" else "error"
    except Exception as e:
        status = "error"
        message = str(e)
        logger.error(f"Trade scan failed: {e}", exc_info=True)

    duration = time.time() - start_time
    _log_run("trade_scan", status, message, trades_executed=total_trades, duration=duration)
    logger.info(f"Trade scan completed in {duration:.2f}s: {total_trades} trades executed")


def run_resolution_check():
    """Check for resolved markets."""
    logger.info("Starting resolution check job...")
    start_time = time.time()
    status = "success"
    message = ""
    resolutions = 0

    try:
        with get_db_session() as db:
            result = _resolution_checker.check_all_open_trades(db)
            resolutions = result.get("resolved", 0)
            message = f"Resolved: {resolutions}, Still open: {result.get('still_open', 0)}, Errors: {result.get('errors', 0)}"
    except Exception as e:
        status = "error"
        message = str(e)
        logger.error(f"Resolution check failed: {e}", exc_info=True)

    duration = time.time() - start_time
    _log_run("resolution_check", status, message, resolutions_processed=resolutions, duration=duration)
    logger.info(f"Resolution check completed in {duration:.2f}s: {resolutions} trades resolved")


def _log_run(job_name, status, message, trades_executed=0, resolutions_processed=0, duration=0):
    """Log a scheduler run."""
    try:
        with get_db_session() as db:
            log = SchedulerLog(
                job_name=job_name,
                status=status,
                message=message[:500] if message else None,
                trades_executed=trades_executed,
                resolutions_processed=resolutions_processed,
                duration_seconds=duration
            )
            db.add(log)
            db.commit()
    except Exception as e:
        logger.error(f"Failed to log scheduler run: {e}")


def is_running() -> bool:
    """Check if scheduler is running."""
    return _scheduler.running
