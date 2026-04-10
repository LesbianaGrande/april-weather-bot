import logging
from fastapi import APIRouter, Request, Path
from database.db import get_db_session
from database.models import Wallet, Trade
from modules.analytics import get_city_stats
from dashboard.app import templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/wallets")
async def wallets_page(request: Request):
    """Wallets overview page."""
    try:
        with get_db_session() as db:
            wallets_data = []

            for strategy_id in ["strategy1", "strategy2"]:
                wallet = db.query(Wallet).filter(Wallet.strategy_id == strategy_id).first()

                if wallet:
                    open_trades = db.query(Trade).filter(
                        Trade.strategy_id == strategy_id,
                        Trade.status == "open"
                    ).all()

                    city_stats = get_city_stats(strategy_id, db)

                    open_trades_data = []
                    for trade in open_trades[:10]:
                        open_trades_data.append({
                            "id": trade.id,
                            "city": trade.city,
                            "shares": trade.shares,
                            "fill_price": f"{trade.avg_fill_price:.4f}",
                            "cost": f"${trade.total_cost:.2f}",
                            "opened": trade.opened_at.strftime("%Y-%m-%d %H:%M"),
                        })

                    # Recent closed trades
                    closed_trades = db.query(Trade).filter(
                        Trade.strategy_id == strategy_id,
                        Trade.status.in_(["won", "lost"])
                    ).order_by(Trade.resolved_at.desc()).limit(10).all()

                    closed_trades_data = []
                    for trade in closed_trades:
                        closed_trades_data.append({
                            "city": trade.city,
                            "status": trade.status,
                            "pnl": f"${trade.pnl:.2f}" if trade.pnl else "-",
                            "resolved": trade.resolved_at.strftime("%Y-%m-%d %H:%M") if trade.resolved_at else "-",
                            "status_color": "green" if trade.status == "won" else "red"
                        })

                    wallets_data.append({
                        "strategy_id": strategy_id,
                        "name": wallet.name,
                        "balance": f"${wallet.balance:.2f}",
                        "starting_balance": f"${wallet.starting_balance:.2f}",
                        "pnl": f"${wallet.pnl:.2f}",
                        "pnl_pct": f"{wallet.pnl_pct:.2f}%",
                        "pnl_color": "green" if wallet.pnl >= 0 else "red",
                        "open_count": len(open_trades),
                        "total_trades": len(db.query(Trade).filter(Trade.strategy_id == strategy_id).all()),
                        "open_trades": open_trades_data,
                        "closed_trades": closed_trades_data,
                        "city_stats": city_stats[:15],
                    })

            return templates.TemplateResponse("wallets.html", {
                "request": request,
                "wallets": wallets_data,
            })
    except Exception as e:
        logger.error(f"Error rendering wallets: {e}", exc_info=True)
        return templates.TemplateResponse("wallets.html", {
            "request": request,
            "error": str(e),
            "wallets": [],
        })


@router.get("/wallets/{strategy_id}")
async def wallet_detail(request: Request, strategy_id: str = Path(...)):
    """Individual wallet detail page."""
    try:
        with get_db_session() as db:
            wallet = db.query(Wallet).filter(Wallet.strategy_id == strategy_id).first()

            if not wallet:
                return templates.TemplateResponse("wallets.html", {
                    "request": request,
                    "error": f"Wallet not found: {strategy_id}",
                    "wallets": [],
                })

            all_trades = db.query(Trade).filter(Trade.strategy_id == strategy_id).all()
            open_trades = [t for t in all_trades if t.status == "open"]
            closed_trades = [t for t in all_trades if t.status in ["won", "lost"]]

            open_trades_data = []
            for trade in sorted(open_trades, key=lambda x: x.opened_at, reverse=True)[:20]:
                open_trades_data.append({
                    "id": trade.id,
                    "city": trade.city,
                    "question": trade.question[:60] + "..." if len(trade.question) > 60 else trade.question,
                    "shares": trade.shares,
                    "fill_price": f"{trade.avg_fill_price:.4f}",
                    "cost": f"${trade.total_cost:.2f}",
                    "opened": trade.opened_at.strftime("%Y-%m-%d %H:%M"),
                })

            closed_trades_data = []
            for trade in sorted(closed_trades, key=lambda x: x.resolved_at or x.opened_at, reverse=True)[:20]:
                closed_trades_data.append({
                    "city": trade.city,
                    "status": trade.status,
                    "pnl": f"${trade.pnl:.2f}" if trade.pnl else "-",
                    "resolved": trade.resolved_at.strftime("%Y-%m-%d %H:%M") if trade.resolved_at else "-",
                    "status_color": "green" if trade.status == "won" else "red"
                })

            city_stats = get_city_stats(strategy_id, db)

            wallet_data = {
                "strategy_id": strategy_id,
                "name": wallet.name,
                "balance": f"${wallet.balance:.2f}",
                "starting_balance": f"${wallet.starting_balance:.2f}",
                "pnl": f"${wallet.pnl:.2f}",
                "pnl_pct": f"{wallet.pnl_pct:.2f}%",
                "pnl_color": "green" if wallet.pnl >= 0 else "red",
                "open_count": len(open_trades),
                "total_trades": len(all_trades),
                "open_trades": open_trades_data,
                "closed_trades": closed_trades_data,
                "city_stats": city_stats,
            }

            return templates.TemplateResponse("wallets.html", {
                "request": request,
                "wallets": [wallet_data],
            })
    except Exception as e:
        logger.error(f"Error rendering wallet detail: {e}", exc_info=True)
        return templates.TemplateResponse("wallets.html", {
            "request": request,
            "error": str(e),
            "wallets": [],
        })
