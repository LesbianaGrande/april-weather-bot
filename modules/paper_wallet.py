import logging
from datetime import datetime
from typing import Optional
from database.models import Wallet, Trade
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class PaperWallet:
    """Namespace object passed to strategies; actual logic uses module-level functions."""
    pass


def get_wallet(strategy_id: str, db: Session) -> Optional[Wallet]:
    """Get or create a wallet for a strategy."""
    wallet = db.query(Wallet).filter(Wallet.strategy_id == strategy_id).first()
    if not wallet:
        logger.warning(f"Wallet not found for strategy {strategy_id}")
        return None
    return wallet


def get_balance(strategy_id: str, db: Session) -> float:
    """Get current balance for a strategy."""
    wallet = get_wallet(strategy_id, db)
    return wallet.balance if wallet else 0.0


def get_open_positions(strategy_id: str, db: Session) -> list:
    """Get all open trades for a strategy."""
    return db.query(Trade).filter(
        Trade.strategy_id == strategy_id,
        Trade.status == "open"
    ).all()


def execute_trade(
    strategy_id: str,
    market_info,
    shares: int,
    fill_result: dict,
    db: Session,
    forecast_temp: Optional[float] = None,
    reason: Optional[str] = None
) -> Optional[Trade]:
    """
    Deduct cost from wallet balance and record the trade.
    Returns the Trade object if successful, None if insufficient balance.
    """
    wallet = get_wallet(strategy_id, db)
    if not wallet:
        logger.error(f"Cannot execute trade: wallet not found for {strategy_id}")
        return None

    total_cost = fill_result.get("total_cost", 0)
    avg_fill_price = fill_result.get("avg_fill_price", 0)

    if wallet.balance < total_cost:
        logger.warning(f"Insufficient balance: {wallet.balance} < {total_cost}")
        return None

    # Deduct from wallet
    wallet.balance -= total_cost
    wallet.updated_at = datetime.utcnow()

    # Create trade record
    trade = Trade(
        wallet_id=wallet.id,
        strategy_id=strategy_id,
        market_id=market_info.market_id,
        condition_id=market_info.condition_id,
        city=market_info.city,
        market_date=market_info.market_date,
        question=market_info.question,
        position="NO",
        token_id=market_info.no_token_id,
        shares=shares,
        avg_fill_price=avg_fill_price,
        total_cost=total_cost,
        status="open",
        opened_at=datetime.utcnow(),
        temperature_threshold=market_info.temperature_threshold_raw,
        temperature_unit=market_info.temperature_unit,
        forecast_temp=forecast_temp,
        trade_reason=reason
    )

    try:
        db.add(trade)
        db.add(wallet)
        db.commit()
        logger.info(
            f"Trade executed: {strategy_id} / {market_info.city} / "
            f"{shares} shares @ {avg_fill_price:.4f} = ${total_cost:.2f}"
        )
        return trade
    except Exception as e:
        logger.error(f"Error executing trade: {e}")
        db.rollback()
        return None


def settle_trade(trade_id: int, resolution: str, db: Session) -> Optional[Trade]:
    """
    Settle a trade based on market resolution.
    resolution: "YES" or "NO"
    If we bought NO (position=="NO"):
        - resolution == "NO" (we win): pnl = +shares * (1 - fill_price)
        - resolution == "YES" (we lose): pnl = -total_cost
    """
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade:
        logger.error(f"Trade not found: {trade_id}")
        return None

    wallet = trade.wallet
    resolution = resolution.upper()

    if trade.position == "NO":
        if resolution == "NO":
            # We won
            pnl = trade.shares * (1.0 - trade.avg_fill_price)
            trade.status = "won"
        else:
            # We lost
            pnl = -trade.total_cost
            trade.status = "lost"
    else:
        # position == "YES"
        if resolution == "YES":
            pnl = trade.shares * (1.0 - trade.avg_fill_price)
            trade.status = "won"
        else:
            pnl = -trade.total_cost
            trade.status = "lost"

    trade.pnl = pnl
    trade.resolved_at = datetime.utcnow()
    wallet.balance += pnl
    wallet.updated_at = datetime.utcnow()

    try:
        db.add(trade)
        db.add(wallet)
        db.commit()
        logger.info(f"Trade settled: {trade_id} / {trade.status} / PnL: ${pnl:.2f}")
        return trade
    except Exception as e:
        logger.error(f"Error settling trade: {e}")
        db.rollback()
        return None
