from abc import ABC, abstractmethod
from sqlalchemy.orm import Session


class BaseStrategy(ABC):
    STRATEGY_ID: str = ""
    NAME: str = ""

    def __init__(self, market_scanner, weather_service, order_book, paper_wallet, risk_manager):
        self.market_scanner = market_scanner
        self.weather_service = weather_service
        self.order_book = order_book
        self.paper_wallet = paper_wallet
        self.risk_manager = risk_manager

    @abstractmethod
    def run_scan(self, db: Session) -> int:
        """Execute the strategy scan. Returns number of trades executed."""
        pass

    def get_strategy_id(self) -> str:
        return self.STRATEGY_ID

    def get_name(self) -> str:
        return self.NAME
