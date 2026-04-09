from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class Wallet(Base):
    __tablename__ = "wallets"
    id = Column(Integer, primary_key=True)
    strategy_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    balance = Column(Float, default=10000.0)
    starting_balance = Column(Float, default=10000.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    trades = relationship("Trade", back_populates="wallet")

    @property
    def pnl(self):
        return self.balance - self.starting_balance

    @property
    def pnl_pct(self):
        if self.starting_balance == 0:
            return 0.0
        return (self.pnl / self.starting_balance) * 100


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"))
    strategy_id = Column(String, nullable=False)
    market_id = Column(String, nullable=False)
    condition_id = Column(String, nullable=True)
    city = Column(String, nullable=False)
    market_date = Column(Date, nullable=False)
    question = Column(String, nullable=False)
    position = Column(String, default="NO")
    token_id = Column(String, nullable=True)
    shares = Column(Integer, nullable=False)
    avg_fill_price = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)
    status = Column(String, default="open")  # open, won, lost
    opened_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    pnl = Column(Float, nullable=True)
    temperature_threshold = Column(Float, nullable=True)
    forecast_temp = Column(Float, nullable=True)
    temperature_unit = Column(String, default="C")
    trade_reason = Column(Text, nullable=True)
    wallet = relationship("Wallet", back_populates="trades")


class DailyTradeCount(Base):
    __tablename__ = "daily_trade_counts"
    id = Column(Integer, primary_key=True)
    strategy_id = Column(String, nullable=False)
    city = Column(String, nullable=False)
    market_date = Column(Date, nullable=False)
    trade_date = Column(Date, nullable=False)
    count = Column(Integer, default=0)


class MarketCache(Base):
    __tablename__ = "market_cache"
    id = Column(Integer, primary_key=True)
    market_id = Column(String, unique=True, nullable=False)
    condition_id = Column(String, nullable=True)
    question = Column(String, nullable=False)
    city = Column(String, nullable=False)
    market_date = Column(Date, nullable=False)
    temperature_threshold = Column(Float, nullable=True)
    temperature_unit = Column(String, nullable=True)
    direction = Column(String, nullable=True)  # "higher" or "lower"
    yes_token_id = Column(String, nullable=True)
    no_token_id = Column(String, nullable=True)
    yes_price = Column(Float, nullable=True)
    no_price = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    is_resolved = Column(Boolean, default=False)
    resolution = Column(String, nullable=True)
    end_date = Column(DateTime, nullable=True)
    cached_at = Column(DateTime, default=datetime.utcnow)


class SchedulerLog(Base):
    __tablename__ = "scheduler_logs"
    id = Column(Integer, primary_key=True)
    job_name = Column(String, nullable=False)
    run_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, nullable=False)  # success, error
    message = Column(Text, nullable=True)
    trades_executed = Column(Integer, default=0)
    resolutions_processed = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
