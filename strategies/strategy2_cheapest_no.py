import logging
from datetime import datetime
from config.cities import is_eligible_for_strategy
from strategies.base_strategy import BaseStrategy
from modules.paper_wallet import execute_trade
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class Strategy2CheapestNo(BaseStrategy):
    STRATEGY_ID = "strategy2"
    NAME = "Cheapest NO"

    def run_scan(self, db: Session) -> int:
        """
        Strategy 2: Buy cheapest NO tokens
        - Get markets for tomorrow and day after
        - Filter to cities eligible for strategy2
        - For each eligible market: check daily limit, get NO ask price
        - Build candidates list: [(no_ask_price, market, market_date)]
        - Sort by no_ask_price ascending (cheapest first)
        - For each candidate: re-check daily limit, get position size, simulate fill, execute trade, increment count
        """
        logger.info(f"Running {self.NAME} strategy...")

        # Get markets
        markets = self.market_scanner.scan_markets(db)
        if not markets:
            logger.info("No markets found")
            return 0

        # Build candidates
        candidates = []
        for market_info in markets:
            try:
                if not is_eligible_for_strategy(market_info.city, self.STRATEGY_ID):
                    logger.debug(f"City {market_info.city} not eligible for {self.STRATEGY_ID}")
                    continue

                # Get best NO ask
                best_ask = self.order_book.get_best_ask(market_info.no_token_id)
                if best_ask is None:
                    logger.debug(f"No ask price found for {market_info.city}")
                    continue

                candidates.append((best_ask, market_info))

            except Exception as e:
                logger.error(f"Error processing market {market_info.market_id}: {e}")
                continue

        # Sort by ask price (cheapest first)
        candidates.sort(key=lambda x: x[0])

        trades_executed = 0

        for best_ask, market_info in candidates:
            try:
                # Re-check daily trade limit
                if not self.risk_manager.check_daily_trade_limit(
                    self.STRATEGY_ID, market_info.city, market_info.market_date, db
                ):
                    logger.debug(f"Daily trade limit reached for {market_info.city} on {market_info.market_date}")
                    continue

                # Get position size
                shares = self.risk_manager.get_position_size(self.STRATEGY_ID, market_info.city, db)

                # Simulate order book fill
                fill_result = self.order_book.simulate_buy(market_info.no_token_id, shares)
                if not fill_result:
                    logger.debug(f"Insufficient liquidity for {market_info.city} NO token")
                    continue

                # Execute trade
                reason = f"Cheapest NO: {best_ask:.4f} ask"
                trade = execute_trade(
                    self.STRATEGY_ID,
                    market_info,
                    shares,
                    fill_result,
                    db,
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
