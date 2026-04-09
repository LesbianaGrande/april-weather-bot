import logging
from datetime import datetime, timedelta, date
from config.settings import LOSS_THRESHOLD, LOSS_WINDOW_DAYS, DEFAULT_SHARES, REDUCED_SHARES, MAX_TRADES_PER_MARKET_PER_DAY
from database.models import Trade, DailyTradeCount

logger = logging.getLogger(__name__)


def get_position_size(strategy_id: str, city: str, db) -> int:
    """
    Returns REDUCED_SHARES if city has > LOSS_THRESHOLD losses in past LOSS_WINDOW_DAYS,
    else DEFAULT_SHARES.
    """
    cutoff = datetime.utcnow() - timedelta(days=LOSS_WINDOW_DAYS)
    losses = db.query(Trade).filter(
        Trade.strategy_id == strategy_id,
        Trade.city == city,
        Trade.status == "lost",
        Trade.resolved_at >= cutoff
    ).count()

    if losses > LOSS_THRESHOLD:
        logger.info(f"Risk reduction for {strategy_id}/{city}: {losses} losses in {LOSS_WINDOW_DAYS} days")
        return REDUCED_SHARES
    return DEFAULT_SHARES


def check_daily_trade_limit(strategy_id: str, city: str, market_date: date, db) -> bool:
    """
    Returns True if we can still trade this city/date combo today.
    """
    today = date.today()
    count = db.query(DailyTradeCount).filter(
        DailyTradeCount.strategy_id == strategy_id,
        DailyTradeCount.city == city,
        DailyTradeCount.market_date == market_date,
        DailyTradeCount.trade_date == today
    ).first()

    if count is None:
        return True

    return count.count < MAX_TRADES_PER_MARKET_PER_DAY


def increment_daily_trade_count(strategy_id: str, city: str, market_date: date, db):
    """Increment the daily trade count."""
    today = date.today()
    count = db.query(DailyTradeCount).filter(
        DailyTradeCount.strategy_id == strategy_id,
        DailyTradeCount.city == city,
        DailyTradeCount.market_date == market_date,
        DailyTradeCount.trade_date == today
    ).first()

    try:
        if count is None:
            count = DailyTradeCount(
                strategy_id=strategy_id,
                city=city,
                market_date=market_date,
                trade_date=today,
                count=1
            )
            db.add(count)
        else:
            count.count += 1
        db.commit()
    except Exception as e:
        logger.error(f"Error incrementing trade count: {e}")
        db.rollback()


def get_city_loss_info(strategy_id: str, city: str, db) -> dict:
    """Returns info about city's recent loss record for display."""
    cutoff = datetime.utcnow() - timedelta(days=LOSS_WINDOW_DAYS)

    losses = db.query(Trade).filter(
        Trade.strategy_id == strategy_id,
        Trade.city == city,
        Trade.status == "lost",
        Trade.resolved_at >= cutoff
    ).count()

    total = db.query(Trade).filter(
        Trade.strategy_id == strategy_id,
        Trade.city == city,
        Trade.resolved_at >= cutoff
    ).count()

    return {
        "losses": losses,
        "total": total,
        "window_days": LOSS_WINDOW_DAYS,
        "reduced_shares": losses > LOSS_THRESHOLD
    }
