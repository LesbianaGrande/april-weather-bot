import logging
from datetime import datetime
from config.settings import TEMP_PROXIMITY_C
from config.cities import is_eligible_for_strategy
from strategies.base_strategy import BaseStrategy
from modules.paper_wallet import execute_trade, get_wallet
import modules.paper_wallet as pw
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class Strategy1AgainstForecast(BaseStrategy):
    STRATEGY_ID = "strategy1"
    NAME = "Against Forecast"

    def run_scan(self, db: Session) -> int:
        """
        Strategy 1: Trade against forecast
        - Get markets for tomorrow and day after
        - For each market: check if |threshold_c - forecast_high_c| <= TEMP_PROXIMITY_C
        - For "higher" markets: bet NO if forecast >= threshold
        - For "lower" markets: bet NO if forecast <= threshold
        """
        logger.info(f"Running {self.NAME} strategy...")

        # Get markets
        markets = self.market_scanner.scan_markets(db)
        if not markets:
            logger.info("No markets found")
            return 0

        trades_executed = 0

        for market_info in markets:
            try:
                # Check city eligibility
                if not is_eligible_for_strategy(market_info.city, self.STRATEGY_ID):
                    logger.debug(f"City {market_info.city} not eligible for {self.STRATEGY_ID}")
                    continue

                # Get forecast
                forecast = self.weather_service.get_forecast_high_c(market_info.city, market_info.market_date)
                if forecast is None:
                    logger.debug(f"No forecast for {market_info.city} on {market_info.market_date}")
                    continue

                # Check proximity
                proximity = abs(market_info.temperature_threshold - forecast)
                if proximity > TEMP_PROXIMITY_C:
                    logger.debug(f"Forecast {forecast}°C not within {TEMP_PROXIMITY_C}°C of threshold {market_info.temperature_threshold}°C")
                    continue

                # Determine if we should trade
                should_trade = False
                reason = ""

                if market_info.direction == "higher":
                    # "higher than X°C" - we bet NO if forecast says it will meet or beat
                    if forecast >= market_info.temperature_threshold:
                        should_trade = True
                        reason = f"Forecast {forecast:.1f}°C >= threshold {market_info.temperature_threshold:.1f}°C"
                elif market_info.direction == "lower":
                    # "lower than X°C" - we bet NO if forecast says it will be at or under
                    if forecast <= market_info.temperature_threshold:
                        should_trade = True
                        reason = f"Forecast {forecast:.1f}°C <= threshold {market_info.temperature_threshold:.1f}°C"

                if not should_trade:
                    continue

                # Check daily trade limit
                if not self.risk_manager.check_daily_trade_limit(
                    self.STRATEGY_ID, market_info.city, market_info.market_date, db
                ):
                    logger.info(f"Daily trade limit reached for {market_info.city} on {market_info.market_date}")
                    continue

                # Get position size
                shares = self.risk_manager.get_position_size(self.STRATEGY_ID, market_info.city, db)

                # Simulate order book fill
                fill_result = self.order_book.simulate_buy(market_info.no_token_id, shares)
                if not fill_result:
                    logger.debug(f"Insufficient liquidity for {market_info.city} NO token")
                    continue

                # Execute trade
                trade = execute_trade(
                    self.STRATEGY_ID,
                    market_info,
                    shares,
                    fill_result,
                    db,
                    forecast_temp=forecast,
                    reason=reason
                )

                if trade:
                    self.risk_manager.increment_daily_trade_count(
                        self.STRATEGY_ID, market_info.city, market_info.market_date, db
                    )
                    trades_executed += 1

            except Exception as e:
                logger.error(f"Error processing market {market_info.market_id}: {e}", exc_info=True)
                continue

        logger.info(f"{self.NAME} strategy executed {trades_executed} trades")
        return trades_executed
