import os
import logging
import uvicorn
from database.db import init_db, get_db_session
from database.models import Wallet
from dashboard.app import create_app
from scheduler.jobs import setup_scheduler, start as start_scheduler
from modules.market_scanner import MarketScanner
from modules.weather_service import WeatherService
from modules.order_book import OrderBook
from modules.paper_wallet import PaperWallet
from modules.risk_manager import RiskManager
from modules.resolution_checker import ResolutionChecker
from strategies.strategy1_against_forecast import Strategy1AgainstForecast
from strategies.strategy2_cheapest_no import Strategy2CheapestNo
from config.settings import PORT, STARTING_BALANCE, LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    logger.info("Starting Polymarket Weather Bot...")

    # Initialize database
    init_db()
    logger.info("Database initialized")

    # Create wallets if they don't exist
    with get_db_session() as db:
        for strategy_id, name in [("strategy1", "Against Forecast"), ("strategy2", "Cheapest NO")]:
            existing = db.query(Wallet).filter(Wallet.strategy_id == strategy_id).first()
            if not existing:
                db.add(Wallet(
                    strategy_id=strategy_id,
                    name=name,
                    balance=STARTING_BALANCE,
                    starting_balance=STARTING_BALANCE
                ))
                logger.info(f"Created wallet for {strategy_id}: {name}")
        db.commit()

    # Instantiate modules
    logger.info("Initializing trading modules...")
    market_scanner = MarketScanner()
    weather_service = WeatherService()
    order_book = OrderBook()
    paper_wallet = PaperWallet()
    risk_manager = RiskManager()
    resolution_checker = ResolutionChecker()

    # Instantiate strategies
    strategy1 = Strategy1AgainstForecast(market_scanner, weather_service, order_book, paper_wallet, risk_manager)
    strategy2 = Strategy2CheapestNo(market_scanner, weather_service, order_book, paper_wallet, risk_manager)
    logger.info(f"Strategy 1: {strategy1.NAME}")
    logger.info(f"Strategy 2: {strategy2.NAME}")

    # Setup and start scheduler
    logger.info("Setting up scheduler...")
    setup_scheduler([strategy1, strategy2], resolution_checker)
    start_scheduler()

    # Create FastAPI app
    logger.info("Creating FastAPI application...")
    app = create_app()

    # Start web server
    logger.info(f"Starting web server on 0.0.0.0:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level=LOG_LEVEL.lower())


if __name__ == "__main__":
    main()
