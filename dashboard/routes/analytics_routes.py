import logging
import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from database.db import get_db_session
from modules.analytics import (
    get_wallet_stats, get_city_stats, get_daily_pnl,
    get_trades_per_day
)
from dashboard.app import templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/analytics")
async def analytics_page(request: Request):
    """Analytics dashboard."""
    try:
        with get_db_session() as db:
            stats1 = get_wallet_stats("strategy1", db)
            stats2 = get_wallet_stats("strategy2", db)

            city_stats1 = get_city_stats("strategy1", db)
            city_stats2 = get_city_stats("strategy2", db)

            daily_pnl1 = get_daily_pnl("strategy1", db, days=30)
            daily_pnl2 = get_daily_pnl("strategy2", db, days=30)

            trades_per_day = get_trades_per_day(db, days=30)

            # Prepare chart data
            pnl_dates = [d["date"] for d in daily_pnl1]
            pnl1_values = [d["cumulative_pnl"] for d in daily_pnl1]
            pnl2_values = [d["cumulative_pnl"] for d in daily_pnl2]

            trades_dates = [d["date"] for d in trades_per_day]
            trades_counts = [d["count"] for d in trades_per_day]

            # Overall stats
            total_pnl = stats1["pnl"] + stats2["pnl"]
            total_trades = stats1["total_trades"] + stats2["total_trades"]
            overall_won = stats1["won_trades"] + stats2["won_trades"]
            overall_lost = stats1["lost_trades"] + stats2["lost_trades"]
            overall_win_rate = (overall_won / total_trades * 100) if total_trades > 0 else 0
            total_volume = stats1["total_volume"] + stats2["total_volume"]

            return templates.TemplateResponse("analytics.html", {
                "request": request,
                "total_pnl": f"${total_pnl:.2f}",
                "total_trades": total_trades,
                "overall_win_rate": f"{overall_win_rate:.1f}%",
                "total_volume": f"${total_volume:.2f}",
                "pnl_dates_json": json.dumps(pnl_dates),
                "pnl1_values_json": json.dumps(pnl1_values),
                "pnl2_values_json": json.dumps(pnl2_values),
                "trades_dates_json": json.dumps(trades_dates),
                "trades_counts_json": json.dumps(trades_counts),
                "city_stats1": city_stats1[:10],
                "city_stats2": city_stats2[:10],
                "stats1": stats1,
                "stats2": stats2,
            })
    except Exception as e:
        logger.error(f"Error rendering analytics: {e}", exc_info=True)
        return templates.TemplateResponse("analytics.html", {
            "request": request,
            "error": str(e),
            "total_pnl": "$0.00",
            "total_trades": 0,
            "overall_win_rate": "0%",
            "total_volume": "$0.00",
            "pnl_dates_json": "[]",
            "pnl1_values_json": "[]",
            "pnl2_values_json": "[]",
            "trades_dates_json": "[]",
            "trades_counts_json": "[]",
            "city_stats1": [],
            "city_stats2": [],
            "stats1": {},
            "stats2": {},
        })


@router.get("/api/analytics/summary")
async def api_analytics_summary():
    """API endpoint for analytics summary (JSON)."""
    try:
        with get_db_session() as db:
            stats1 = get_wallet_stats("strategy1", db)
            stats2 = get_wallet_stats("strategy2", db)

            return JSONResponse({
                "strategy1": stats1,
                "strategy2": stats2,
            })
    except Exception as e:
        logger.error(f"Error fetching analytics: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
