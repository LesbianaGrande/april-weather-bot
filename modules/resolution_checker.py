import logging
import requests
from datetime import datetime
from typing import Optional
from config.settings import GAMMA_API_BASE, API_RETRY_COUNT, API_RETRY_DELAY
from database.models import Trade
import time

logger = logging.getLogger(__name__)


class ResolutionChecker:
    def _make_request(self, url: str, max_retries: int = API_RETRY_COUNT) -> Optional[dict]:
        """Make HTTP request with retry logic."""
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Resolution check request failed (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(API_RETRY_DELAY)
                else:
                    logger.error(f"Resolution check request failed after {max_retries} attempts: {e}")
                    return None

    def check_market_resolution(self, market_id: str) -> Optional[str]:
        """
        Check if a market is resolved and return the winning outcome.
        Returns "YES", "NO", or None if unresolved.
        """
        url = f"{GAMMA_API_BASE}/markets/{market_id}"
        market = self._make_request(url)

        if not market:
            logger.warning(f"Could not fetch market data: {market_id}")
            return None

        # Check if market is closed/resolved
        if not (market.get("closed") or market.get("resolved")):
            return None

        # Try to find winning token (price >= 0.99)
        tokens = market.get("tokens", [])
        for token in tokens:
            price = float(token.get("price", 0))
            if price >= 0.99:
                outcome = token.get("outcome", "").upper()
                logger.info(f"Market {market_id} resolved: {outcome}")
                return outcome

        # Fallback: check outcomePrices array
        outcomes = market.get("outcomes", [])
        prices = market.get("outcomePrices", [])
        if outcomes and prices:
            for outcome, price in zip(outcomes, prices):
                try:
                    if float(price) >= 0.99:
                        logger.info(f"Market {market_id} resolved: {outcome.upper()}")
                        return outcome.upper()
                except (ValueError, TypeError):
                    pass

        logger.warning(f"Market {market_id} is closed but no clear winner found")
        return None

    def check_all_open_trades(self, db) -> dict:
        """
        Check all open trades for resolution.
        Returns {"resolved": int, "still_open": int, "errors": int}
        """
        open_trades = db.query(Trade).filter(Trade.status == "open").all()

        resolved_count = 0
        still_open_count = 0
        error_count = 0

        for trade in open_trades:
            try:
                resolution = self.check_market_resolution(trade.market_id)

                if resolution:
                    # Settle the trade
                    trade.status = "won" if (trade.position == "NO" and resolution == "NO") or (trade.position == "YES" and resolution == "YES") else "lost"

                    if trade.status == "won":
                        pnl = trade.shares * (1.0 - trade.avg_fill_price)
                    else:
                        pnl = -trade.total_cost

                    trade.pnl = pnl
                    trade.resolved_at = datetime.utcnow()
                    trade.wallet.balance += pnl
                    trade.wallet.updated_at = datetime.utcnow()

                    db.add(trade)
                    resolved_count += 1
                    logger.info(f"Resolved trade {trade.id}: {trade.status} / PnL: ${pnl:.2f}")
                else:
                    still_open_count += 1

            except Exception as e:
                logger.error(f"Error checking trade {trade.id}: {e}")
                error_count += 1

        try:
            db.commit()
        except Exception as e:
            logger.error(f"Error committing resolutions: {e}")
            db.rollback()

        return {
            "resolved": resolved_count,
            "still_open": still_open_count,
            "errors": error_count
        }
