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
                data = response.json()
                # Polymarket CLOB returns {"error": "..."} with HTTP 200 when no orderbook exists
                if isinstance(data, dict) and data.get("error"):
                    logger.debug(f"CLOB API error for {url}: {data['error']}")
                    return None
                return data
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Order book request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying...")
                    time.sleep(API_RETRY_DELAY)
                else:
                    logger.warning(f"Order book request failed after {max_retries} attempts: {e}")
                    return None

    def fetch_order_book(self, token_id: str) -> Optional[dict]:
        """Fetch order book for a token. Tries /book endpoint (Polymarket CLOB API)."""
        url = f"{CLOB_API_BASE}/book?token_id={token_id}"
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

    def simulate_buy(self, token_id: str, num_shares: int,
                     fallback_price: Optional[float] = None) -> Optional[dict]:
        """
        Simulate buying num_shares at the ask price.

        The Polymarket CLOB API returns asks in DESCENDING price order
        (most expensive first). We sort them ASCENDING (cheapest first)
        so the simulation fills at the best available prices.

        If the order book is unavailable, falls back to fallback_price
        (e.g. the outcomePrices value from the Gamma events API) so
        paper trades still execute.

        Returns:
            {"avg_fill_price": float, "total_cost": float, "fills": list,
             "best_ask": float, "sufficient_liquidity": bool}
        Returns None if no order book data and no fallback_price.
        """
        order_book = self.fetch_order_book(token_id)

        # If order book is unavailable, fall back to market price
        if not order_book or not order_book.get("asks"):
            if fallback_price is not None:
                price = float(fallback_price)
                total_cost = price * num_shares
                logger.info(
                    f"Order book unavailable for token {token_id[:12]}... "
                    f"Using fallback price {price:.4f}"
                )
                return {
                    "avg_fill_price": price,
                    "total_cost": total_cost,
                    "shares_filled": num_shares,
                    "fills": [{"price": price, "shares": num_shares, "cost": total_cost}],
                    "best_ask": price,
                    "sufficient_liquidity": True,
                    "used_fallback": True,
                }
            logger.warning(f"No order book data and no fallback for token {token_id}")
            return None

        # Sort asks ASCENDING by price (cheapest first) — CLOB API returns them descending
        raw_asks = order_book.get("asks", [])
        asks = sorted(raw_asks, key=lambda x: float(x.get("price", 999)))

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
                logger.warning(
                    f"Insufficient liquidity for token {token_id}: "
                    f"requested {num_shares}, got {shares_filled}"
                )

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
                "sufficient_liquidity": sufficient_liquidity,
                "used_fallback": False,
            }

        except (ValueError, TypeError) as e:
            logger.error(f"Error simulating buy: {e}")
            return None
