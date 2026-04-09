import logging
import threading
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


def initialize_backend():
    """Heavy initialization runs in a background thread so uvicorn starts immediately."""
    try:
        logger.info("Background init: starting...")

        init_db()
        logger.info("Background init: database ready")

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
                    logger.info(f"Background init: created wallet for {strategy_id}")
            db.commit()

        market_scanner = MarketScanner()
        weather_service = WeatherService()
        order_book = OrderBook()
        paper_wallet = PaperWallet()
        risk_manager = RiskManager()
        resolution_checker = ResolutionChecker()

        strategy1 = Strategy1AgainstForecast(market_scanner, weather_service, order_book, paper_wallet, risk_manager)
        strategy2 = Strategy2CheapestNo(market_scanner, weather_service, order_book, paper_wallet, risk_manager)
        logger.info(f"Background init: strategies ready ({strategy1.NAME}, {strategy2.NAME})")

        setup_scheduler([strategy1, strategy2], resolution_checker)
        start_scheduler()
        logger.info("Background init: scheduler started — bot is live")

    except Exception as e:
        logger.error(f"Background init failed: {e}", exc_info=True)


def main():
    """Start web server immediately, then init trading backend in background."""
    logger.info("Starting Polymarket Weather Bot...")

    # Kick off heavy init in background — uvicorn starts without waiting for it
    init_thread = threading.Thread(target=initialize_backend, daemon=True)
    init_thread.start()

    # Start web server right away so Railway healthchecks pass immediately
    app = create_app()
    logger.info(f"Starting web server on 0.0.0.0:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level=LOG_LEVEL.lower())


if __name__ == "__main__":
    main()
