import logging
import requests
from typing import Optional
from config.settings import CLOB_API_BASE, API_RETRY_COUNT, API_RETRY_DELAY
import time

logger = logging.getLogger(__name__)


class OrderBook:
    def _make_request(self, url: str, max_retries: int = API_RETRY_COUNT) -> Optional[dict]:
        """Make HTTP request with retry logic."""
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Order book request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying...")
                    time.sleep(API_RETRY_DELAY)
                else:
                    logger.error(f"Order book request failed after {max_retries} attempts: {e}")
                    return None

    def fetch_order_book(self, token_id: str) -> Optional[dict]:
        """Fetch order book for a token."""
        url = f"{CLOB_API_BASE}/order-book?token_id={token_id}"
        return self._make_request(url)

    def get_best_ask(self, token_id: str) -> Optional[float]:
        """Get the lowest ask price for a token."""
        order_book = self.fetch_order_book(token_id)
        if not order_book:
            return None

        asks = order_book.get("asks", [])
        if not asks:
            return None

        try:
            best_ask = min(float(ask.get("price", 999)) for ask in asks)
            return best_ask
        except (ValueError, TypeError):
            return None

    def get_best_bid(self, token_id: str) -> Optional[float]:
        """Get the highest bid price for a token."""
        order_book = self.fetch_order_book(token_id)
        if not order_book:
            return None

        bids = order_book.get("bids", [])
        if not bids:
            return None

        try:
            best_bid = max(float(bid.get("price", 0)) for bid in bids)
            return best_bid
        except (ValueError, TypeError):
            return None

    def simulate_buy(self, token_id: str, num_shares: int) -> Optional[dict]:
        """
        Simulate buying num_shares at the ask price.
        Returns: {"avg_fill_price": float, "total_cost": float, "fills": list, "best_ask": float, "sufficient_liquidity": bool}
        Returns None if order book empty.
        """
        order_book = self.fetch_order_book(token_id)
        if not order_book:
            logger.warning(f"No order book data for token {token_id}")
            return None

        asks = order_book.get("asks", [])
        if not asks:
            logger.warning(f"No asks in order book for token {token_id}")
            return None

        try:
            fills = []
            total_cost = 0.0
            shares_filled = 0
            sufficient_liquidity = True

            for ask in asks:
                if shares_filled >= num_shares:
                    break

                price = float(ask.get("price", 0))
                size = float(ask.get("size", 0))

                shares_to_fill = min(num_shares - shares_filled, size)
                cost = shares_to_fill * price
                total_cost += cost
                shares_filled += shares_to_fill

                fills.append({
                    "price": price,
                    "shares": shares_to_fill,
                    "cost": cost
                })

            if shares_filled < num_shares:
                sufficient_liquidity = False
                logger.warning(f"Insufficient liquidity for token {token_id}: requested {num_shares}, got {shares_filled}")

            if shares_filled == 0:
                return None

            avg_fill_price = total_cost / shares_filled if shares_filled > 0 else 0

            best_ask = float(asks[0].get("price", 0)) if asks else 0

            return {
                "avg_fill_price": avg_fill_price,
                "total_cost": total_cost,
                "shares_filled": shares_filled,
                "fills": fills,
                "best_ask": best_ask,
                "sufficient_liquidity": sufficient_liquidity
            }

        except (ValueError, TypeError) as e:
            logger.error(f"Error simulating buy: {e}")
            return None
