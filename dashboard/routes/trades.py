import logging
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from database.db import get_db_session
from database.models import Trade
from dashboard.app import templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/trades")
async def trades_page(
    request: Request,
    strategy: str = Query(None),
    city: str = Query(None),
    status: str = Query(None),
    limit: int = Query(100)
):
    """Trades page with filtering."""
    try:
        with get_db_session() as db:
            query = db.query(Trade)

            if strategy:
                query = query.filter(Trade.strategy_id == strategy)
            if city:
                query = query.filter(Trade.city == city)
            if status:
                query = query.filter(Trade.status == status)

            total_count = query.count()
            trades = query.order_by(Trade.opened_at.desc()).limit(limit).all()

            trades_data = []
            for trade in trades:
                trades_data.append({
                    "id": trade.id,
                    "date": trade.opened_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "strategy": trade.strategy_id,
                    "city": trade.city,
                    "question": trade.question[:80] + "..." if len(trade.question) > 80 else trade.question,
                    "shares": trade.shares,
                    "fill_price": f"{trade.avg_fill_price:.4f}",
                    "cost": f"${trade.total_cost:.2f}",
                    "status": trade.status,
                    "pnl": f"${trade.pnl:.2f}" if trade.pnl else "-",
                    "status_color": "green" if trade.status == "won" else "red" if trade.status == "lost" else "yellow"
                })

            # Get available filters
            strategies = db.query(Trade.strategy_id).distinct().all()
            cities = db.query(Trade.city).distinct().all()
            statuses = ["open", "won", "lost"]

            return templates.TemplateResponse("trades.html", {
                "request": request,
                "trades": trades_data,
                "total_count": total_count,
                "strategies": [s[0] for s in strategies],
                "cities": [c[0] for c in cities],
                "statuses": statuses,
                "current_strategy": strategy,
                "current_city": city,
                "current_status": status,
                "current_limit": limit,
            })
    except Exception as e:
        logger.error(f"Error rendering trades: {e}", exc_info=True)
        return templates.TemplateResponse("trades.html", {
            "request": request,
            "error": str(e),
            "trades": [],
            "total_count": 0,
            "strategies": [],
            "cities": [],
            "statuses": [],
            "current_strategy": strategy,
            "current_city": city,
            "current_status": status,
        })


@router.get("/api/trades")
async def api_trades(
    strategy: str = Query(None),
    city: str = Query(None),
    status: str = Query(None),
    limit: int = Query(100)
):
    """API endpoint for trades (JSON)."""
    try:
        with get_db_session() as db:
            query = db.query(Trade)

            if strategy:
                query = query.filter(Trade.strategy_id == strategy)
            if city:
                query = query.filter(Trade.city == city)
            if status:
                query = query.filter(Trade.status == status)

            trades = query.order_by(Trade.opened_at.desc()).limit(limit).all()

            trades_data = []
            for trade in trades:
                trades_data.append({
                    "id": trade.id,
                    "date": trade.opened_at.isoformat(),
                    "strategy": trade.strategy_id,
                    "city": trade.city,
                    "question": trade.question,
                    "shares": trade.shares,
                    "fill_price": trade.avg_fill_price,
                    "cost": trade.total_cost,
                    "status": trade.status,
                    "pnl": trade.pnl,
                })

            return JSONResponse(trades_data)
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
