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


def get_daily_pnl(strategy_id: str, db, days: int = 30) -> list:
    """Daily P&L for the last N days."""
    trades = db.query(Trade).filter(
        Trade.strategy_id == strategy_id,
        Trade.status.in_(["won", "lost"]),
        Trade.resolved_at >= datetime.utcnow() - timedelta(days=days)
    ).all()

    daily_map = {}
    for trade in trades:
        if trade.resolved_at:
            day = trade.resolved_at.date()
            if day not in daily_map:
                daily_map[day] = 0
            daily_map[day] += trade.pnl if trade.pnl else 0

    results = []
    cumulative = 0
    for i in range(days, -1, -1):
        current_date = (datetime.utcnow() - timedelta(days=i)).date()
        daily_pnl = daily_map.get(current_date, 0)
        cumulative += daily_pnl
        results.append({
            "date": current_date.isoformat(),
            "pnl": round(daily_pnl, 2),
            "cumulative_pnl": round(cumulative, 2)
        })

    return results


def get_recent_trades(db, limit: int = 20, strategy_id: str = None) -> list:
    """Recent trades for the dashboard."""
    query = db.query(Trade).order_by(Trade.opened_at.desc()).limit(limit)

    if strategy_id:
        query = query.filter(Trade.strategy_id == strategy_id)

    trades = query.all()

    results = []
    for trade in trades:
        results.append({
            "id": trade.id,
            "date": trade.opened_at.isoformat() if trade.opened_at else "",
            "strategy": trade.strategy_id,
            "city": trade.city or "",
            "question": trade.question or "",
            "market_date": trade.market_date.isoformat() if trade.market_date else "",
            "position": trade.position or "NO",
            "shares": trade.shares or 0,
            "fill_price": round(trade.avg_fill_price, 4) if trade.avg_fill_price else 0.0,
            "cost": round(trade.total_cost, 2) if trade.total_cost else 0.0,
            "status": trade.status,
            "pnl": round(trade.pnl, 2) if trade.pnl else None
        })

    return results


def get_scheduler_health(db) -> dict:
    """Last run times and statuses for each job."""
    jobs = {}

    for job_name in ["trade_scan", "resolution_check"]:
        log = db.query(SchedulerLog).filter(SchedulerLog.job_name == job_name).order_by(SchedulerLog.run_at.desc()).first()

        if log:
            jobs[job_name] = {
                "last_run": log.run_at.isoformat(),
                "status": log.status,
                "message": log.message,
                "trades_executed": log.trades_executed,
                "resolutions_processed": log.resolutions_processed,
                "duration": log.duration_seconds
            }
        else:
            jobs[job_name] = {
                "last_run": None,
                "status": "never",
                "message": "No runs yet",
                "trades_executed": 0,
                "resolutions_processed": 0,
                "duration": 0
            }

    return jobs


def get_trades_per_day(db, days: int = 30) -> list:
    """Trades per day for the last N days."""
    trades = db.query(Trade).filter(
        Trade.opened_at >= datetime.utcnow() - timedelta(days=days)
    ).all()

    daily_map = {}
    for trade in trades:
        day = trade.opened_at.date()
        if day not in daily_map:
            daily_map[day] = 0
        daily_map[day] += 1

    results = []
    for i in range(days, -1, -1):
        current_date = (datetime.utcnow() - timedelta(days=i)).date()
        count = daily_map.get(current_date, 0)
        results.append({
            "date": current_date.isoformat(),
            "count": count
        })

    return results
