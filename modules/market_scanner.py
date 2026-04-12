import logging
import requests
import re
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Optional, List
from config.settings import GAMMA_API_BASE, API_RETRY_COUNT, API_RETRY_DELAY, MARKET_CACHE_TTL_MINUTES
from config.cities import get_city_coords
from database.models import MarketCache
import time

logger = logging.getLogger(__name__)


@dataclass
class MarketInfo:
    market_id: str
    condition_id: str
    question: str
    city: str
    market_date: date
    temperature_threshold: float
    temperature_threshold_raw: float
    temperature_unit: str
    direction: str
    yes_token_id: str
    no_token_id: str
    yes_price: float
    no_price: float
    end_date: datetime


class MarketScanner:
    def __init__(self):
        self.cache = {}

    def _make_request(self, url: str, max_retries: int = API_RETRY_COUNT) -> Optional[dict]:
        """Make HTTP request with retry logic."""
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {API_RETRY_DELAY}s...")
                    time.sleep(API_RETRY_DELAY)
                else:
                    logger.error(f"Request failed after {max_retries} attempts: {e}")
                    return None

    def _parse_date(self, date_str: str, fallback_year: int = None) -> Optional[date]:
        """Parse various date formats."""
        formats = [
            "%B %d, %Y", "%b %d, %Y",
            "%B %d", "%b %d",
            "%d %B %Y", "%d %b %Y",
            "%d %B", "%d %b",
            "%m/%d/%Y", "%m/%d",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                if dt.year == 1900 and fallback_year:
                    dt = dt.replace(year=fallback_year)
                return dt.date()
            except ValueError:
                continue

        logger.warning(f"Could not parse date: {date_str}")
        return None

    def _celsius_to_fahrenheit(self, c: float) -> float:
        return c * 9 / 5 + 32

    def _fahrenheit_to_celsius(self, f: float) -> float:
        return (f - 32) * 5 / 9

    def _extract_market_info(self, market: dict) -> Optional[MarketInfo]:
        """Extract and parse a single market."""
        try:
            market_id = market.get("id")
            condition_id = market.get("conditionId")
            question = market.get("question", "").strip()
            end_date_str = market.get("endDate")

            if not market_id or not question:
                return None

            # Filter: only high temperature markets
            question_lower = question.lower()
            if "low temp" in question_lower or "minimum temp" in question_lower:
                return None
            if not ("high temp" in question_lower or "daily high" in question_lower or "high temperature" in question_lower):
                return None

            # Parse end_date for year inference
            end_date = None
            fallback_year = None
            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                    fallback_year = end_date.year
                except:
                    pass

            # Try multiple regex patterns
            patterns = [
                r"high temperature in ([^,]+?) on ([A-Za-z]+ \d+(?:,? \d{4})?).+?(\d+(?:\.\d+)?)°([CF]) or (higher|lower)",
                r"high temp(?:erature)? in ([^,]+?) on ([A-Za-z]+ \d+(?:,? \d{4})?).+?(\d+(?:\.\d+)?)°([CF]) or (higher|lower)",
                r"([^:]+?): .+high.+?(\d+(?:\.\d+)?)°([CF]) or (higher|lower).+?([A-Za-z]+ \d+)",
                r"daily high.+?in ([^,]+?) on ([A-Za-z]+ \d+(?:,? \d{4})?).+?(\d+(?:\.\d+)?)°([CF]) or (higher|lower)",
            ]

            city = None
            market_date = None
            temp_threshold = None
            temp_unit = None
            direction = None

            for pattern in patterns:
                match = re.search(pattern, question, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    if len(groups) == 5:
                        city, date_str, temp_str, unit, dir_str = groups
                        temp_threshold = float(temp_str)
                        temp_unit = unit.upper()
                        direction = dir_str.lower()
                        market_date = self._parse_date(date_str, fallback_year)
                        break

            if not all([city, market_date, temp_threshold, temp_unit, direction]):
                logger.debug(f"Could not extract all fields from market: {market_id}")
                return None

            # Check if market is for tomorrow or day after
            now = datetime.utcnow().date()
            if market_date not in [now + timedelta(days=1), now + timedelta(days=2)]:
                return None

            # Get token IDs and prices
            yes_token_id = None
            no_token_id = None
            yes_price = None
            no_price = None

            tokens = market.get("tokens", [])
            for token in tokens:
                outcome = token.get("outcome", "").upper()
                token_id = token.get("token_id") or token.get("tokenId")
                price = token.get("price")
                if outcome == "YES":
                    yes_token_id = token_id
                    yes_price = float(price) if price else None
                elif outcome == "NO":
                    no_token_id = token_id
                    no_price = float(price) if price else None

            if not yes_token_id or not no_token_id:
                logger.debug(f"Could not find token IDs for market: {market_id}")
                return None

            # Convert threshold to Celsius for internal use
            threshold_raw = temp_threshold
            if temp_unit == "F":
                temp_threshold = self._fahrenheit_to_celsius(temp_threshold)

            return MarketInfo(
                market_id=market_id,
                condition_id=condition_id,
                question=question,
                city=city.strip(),
                market_date=market_date,
                temperature_threshold=temp_threshold,
                temperature_threshold_raw=threshold_raw,
                temperature_unit=temp_unit,
                direction=direction,
                yes_token_id=yes_token_id,
                no_token_id=no_token_id,
                yes_price=yes_price or 0.5,
                no_price=no_price or 0.5,
                end_date=end_date or datetime.utcnow()
            )
        except Exception as e:
            logger.debug(f"Error extracting market info: {e}")
            return None

    def scan_markets(self, db) -> List[MarketInfo]:
        """Scan Polymarket for weather markets."""
        logger.info("Scanning Polymarket for weather markets...")

        url = f"{GAMMA_API_BASE}/markets?active=true&closed=false&limit=500"
        data = self._make_request(url)

        if not data:
            logger.error("Failed to fetch markets from Polymarket")
            return []

        if isinstance(data, list):
            markets = data
        else:
            markets = data.get("data", data.get("markets", []))
        if isinstance(markets, dict):
            markets = []

        results = []
        for market in markets:
            info = self._extract_market_info(market)
            if info and get_city_coords(info.city):
                results.append(info)
                self._cache_market(db, info)

        logger.info(f"Found {len(results)} valid weather markets")
        return results

    def _cache_market(self, db, market_info: MarketInfo):
        """Store market in cache."""
        try:
            existing = db.query(MarketCache).filter(MarketCache.market_id == market_info.market_id).first()
            if existing:
                existing.yes_price = market_info.yes_price
                existing.no_price = market_info.no_price
                existing.cached_at = datetime.utcnow()
            else:
                cache_entry = MarketCache(
                    market_id=market_info.market_id,
                    condition_id=market_info.condition_id,
                    question=market_info.question,
                    city=market_info.city,
                    market_date=market_info.market_date,
                    temperature_threshold=market_info.temperature_threshold,
                    temperature_unit=market_info.temperature_unit,
                    direction=market_info.direction,
                    yes_token_id=market_info.yes_token_id,
                    no_token_id=market_info.no_token_id,
                    yes_price=market_info.yes_price,
                    no_price=market_info.no_price,
                    is_active=True,
                    end_date=market_info.end_date,
                    cached_at=datetime.utcnow()
                )
                db.add(cache_entry)
            db.commit()
        except Exception as e:
            logger.error(f"Error caching market: {e}")
            db.rollback()

    def refresh_market_cache(self, db):
        """Clear stale cache and re-fetch markets."""
        try:
            cutoff = datetime.utcnow() - timedelta(minutes=MARKET_CACHE_TTL_MINUTES)
            db.query(MarketCache).filter(MarketCache.cached_at < cutoff).delete()
            db.commit()
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            db.rollback()

        return self.scan_markets(db)
