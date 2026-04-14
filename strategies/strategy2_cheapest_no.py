import logging
from datetime import datetime
from config.cities import is_eligible_for_strategy
from config.settings import MAX_TRADES_PER_SCAN
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
        - For each candidate: re-check daily limit, get position size,
          simulate fill (with fallback to outcomePrices), execute trade
        - Stop after MAX_TRADES_PER_SCAN trades to avoid runaway spending
        """
        logger.info(f"Running {self.NAME} strategy...")

        # Get markets
        markets = self.market_scanner.scan_markets(db)
        if not markets:
            logger.info("No markets found")
            return 0

        # Build candidates using outcomePrices as best_ask estimate
        # (CLOB order books for NO tokens often have empty asks, so we
        #  use the Gamma outcomePrices as the primary ranking signal)
        candidates = []
        for market_info in markets:
            try:
                if not is_eligible_for_strategy(market_info.city, self.STRATEGY_ID):
                    logger.debug(f"City {market_info.city} not eligible for {self.STRATEGY_ID}")
                    continue

                # Use the outcomePrices NO price as the ranking signal
                # Fall back to order book only if we have one
                no_price = market_info.no_price
                if no_price <= 0 or no_price >= 1:
                    logger.debug(f"Skipping {market_info.city}: no_price {no_price:.4f} out of range")
                    continue

                # Try to get a live ask; if none, use outcomePrices
                live_ask = self.order_book.get_best_ask(market_info.no_token_id)
                rank_price = live_ask if live_ask is not None else no_price

                candidates.append((rank_price, market_info))
            except Exception as e:
                logger.error(f"Error processing market {market_info.market_id}: {e}")
                continue

        # Sort by ask price (cheapest NO first)
        candidates.sort(key=lambda x: x[0])
        logger.info(f"{self.NAME}: {len(candidates)} candidates, capped at {MAX_TRADES_PER_SCAN}")

        trades_executed = 0
        for rank_price, market_info in candidates:
            # Hard cap: never execute more than MAX_TRADES_PER_SCAN per scan
            if trades_executed >= MAX_TRADES_PER_SCAN:
                logger.info(f"{self.NAME}: reached MAX_TRADES_PER_SCAN ({MAX_TRADES_PER_SCAN}), stopping")
                break

            try:
                # Re-check daily trade limit
                if not self.risk_manager.check_daily_trade_limit(
                    self.STRATEGY_ID, market_info.city, market_info.market_date, db
                ):
                    logger.debug(f"Daily trade limit reached for {market_info.city} on {market_info.market_date}")
                    continue

                # Get position size
                shares = self.risk_manager.get_position_size(self.STRATEGY_ID, market_info.city, db)

                # Simulate order book fill — always pass fallback_price so we
                # can still trade even if the CLOB order book has no asks
                fill_result = self.order_book.simulate_buy(
                    market_info.no_token_id, shares,
                    fallback_price=market_info.no_price
                )
                if not fill_result:
                    logger.debug(f"Insufficient liquidity for {market_info.city} NO token")
                    continue

                # Execute trade
                reason = f"Cheapest NO: {rank_price:.4f} price"
                trade = execute_trade(
                    self.STRATEGY_ID, market_info, shares, fill_result, db, reason=reason
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
