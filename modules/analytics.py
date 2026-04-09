import logging
from datetime import datetime, timedelta, date
from database.models import Trade, Wallet, SchedulerLog
from sqlalchemy import func

logger = logging.getLogger(__name__)


def get_wallet_stats(strategy_id: str, db) -> dict:
    """Get comprehensive wallet statistics."""
    wallet = db.query(Wallet).filter(Wallet.strategy_id == strategy_id).first()

    if not wallet:
        return {
            "balance": 0,
            "starting_balance": 0,
            "pnl": 0,
            "pnl_pct": 0,
            "total_trades": 0,
            "won_trades": 0,
            "lost_trades": 0,
            "open_trades": 0,
            "win_rate": 0,
            "total_volume": 0,
            "avg_trade_cost": 0,
            "best_trade_pnl": 0,
            "worst_trade_pnl": 0,
        }

    trades = db.query(Trade).filter(Trade.strategy_id == strategy_id).all()
    open_trades = [t for t in trades if t.status == "open"]
    resolved_trades = [t for t in trades if t.status in ["won", "lost"]]
    won_trades = [t for t in trades if t.status == "won"]
    lost_trades = [t for t in trades if t.status == "lost"]

    total_trades = len(trades)
    won_count = len(won_trades)
    lost_count = len(lost_trades)
    open_count = len(open_trades)

    total_volume = sum(t.total_cost for t in trades)
    avg_trade_cost = total_volume / total_trades if total_trades > 0 else 0

    win_rate = (won_count / len(resolved_trades) * 100) if resolved_trades else 0

    best_pnl = max([t.pnl for t in resolved_trades], default=0)
    worst_pnl = min([t.pnl for t in resolved_trades], default=0)

    return {
        "balance": wallet.balance,
        "starting_balance": wallet.starting_balance,
        "pnl": wallet.pnl,
        "pnl_pct": wallet.pnl_pct,
        "total_trades": total_trades,
        "won_trades": won_count,
        "lost_trades": lost_count,
        "open_trades": open_count,
        "win_rate": win_rate,
        "total_volume": total_volume,
        "avg_trade_cost": avg_trade_cost,
        "best_trade_pnl": best_pnl,
        "worst_trade_pnl": worst_pnl,
    }


def get_city_stats(strategy_id: str, db) -> list:
    """Per-city breakdown of trades."""
    trades = db.query(Trade).filter(Trade.strategy_id == strategy_id).all()

    city_map = {}
    for trade in trades:
        if trade.city not in city_map:
            city_map[trade.city] = {"wins": 0, "losses": 0, "total_pnl": 0, "trades": 0}

        city_map[trade.city]["trades"] += 1
        if trade.status == "won":
            city_map[trade.city]["wins"] += 1
        elif trade.status == "lost":
            city_map[trade.city]["losses"] += 1

        if trade.pnl:
            city_map[trade.city]["total_pnl"] += trade.pnl

    results = []
    for city, stats in city_map.items():
        resolved = stats["wins"] + stats["losses"]
        win_rate = (stats["wins"] / resolved * 100) if resolved > 0 else 0
        results.append({
            "city": city,
            "trades": stats["trades"],
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate": win_rate,
            "total_pnl": stats["total_pnl"]
        })

    return sorted(results, key=lambda x: x["total_pnl"], reverse=True)
