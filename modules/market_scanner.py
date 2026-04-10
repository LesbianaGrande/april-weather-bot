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
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(API_RETRY_DELAY)
                else:
                    return None

    def scan_markets(self, db):
        url = f"{GAMMA_API_BASE}/markets?active=true&closed=false&limit=500"
        data = self._make_request(url)
        if not data:
            return []
        markets = data.get("data", data.get("markets", []))
        results = []
        for market in markets:
            info = self._extract_market_info(market)
            if info and get_city_coords(info.city):
                results.append(info)
        return results

    def _extract_market_info(self, market):
        try:
            market_id = market.get("id")
            condition_id = market.get("conditionId")
            question = market.get("question", "").strip()
            if not market_id or not question:
                return None
            ql = question.lower()
            if not ("high temp" in ql or "daily high" in ql or "high temperature" in ql):
                return None
            end_date_str = market.get("endDate")
            end_date = None
            fallback_year = None
            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                    fallback_year = end_date.year
                except: pass
            patterns = [
                r"high temperature in ([^,]+?) on ([A-Za-z]+ \d+(?:,? \d{4})?).+?(\d+(?:\.\d+)?)°([CF]) or (higher|lower)",
                r"high temp(?:erature)? in ([^,]+?) on ([A-Za-z]+ \d+(?:,? \d{4})?).+?(\d+(?:\.\d+)?)°([CF]) or (higher|lower)",
            ]
            city = market_date = temp_threshold = temp_unit = direction = None
            import re
            for pat in patterns:
                m = re.search(pat, question, re.IGNORECASE)
                if m and len(m.groups()) == 5:
                    city, dstr, tstr, unit, dstr2 = m.groups()
                    temp_threshold = float(tstr)
                    temp_unit = unit.upper()
                    direction = dstr2.lower()
                    for fmt in ["%B %d, %Y", "%b %d, %Y", "%B %d", "%b %d"]:
                        try:
                            dt = datetime.strptime(dstr.strip(), fmt)
                            if dt.year == 1900 and fallback_year: dt = dt.replace(year=fallback_year)
                            market_date = dt.date(); break
                        except: pass
                    break
            if not all([city, market_date, temp_threshold, temp_unit, direction]):
                return None
            now = datetime.utcnow().date()
            from datetime import timedelta
            if market_date not in [now + timedelta(days=1), now + timedelta(days=2)]:
                return None
            yes_token_id = no_token_id = yes_price = no_price = None
            for tok in market.get("tokens", []):
                out = tok.get("outcome", "").upper()
                tid = tok.get("token_id") or tok.get("tokenId")
                pr = tok.get("price")
                if out == "YES": yes_token_id = tid; yes_price = float(pr) if pr else None
                elif out == "NL�": no_token_id = tid; no_price = float(pr) if pr else None
            if not yes_token_id or not no_token_id:
                return None
            threshold_raw = temp_threshold
            if temp_unit == "F": temp_threshold = (temp_threshold - 32) * 5 / 9
            return MarketInfo(market_id=market_id, condition_id=condition_id, question=question, city=city.strip(), market_date=market_date, temperature_threshold=temp_threshold, temperature_threshold_raw=threshold_raw, temperature_unit=temp_unit, direction=direction, yes_token_id=yes_token_id, no_token_id=no_token_id, yes_price=yes_price or 0.5, no_price=no_price or 0.5, end_date=end_date or datetime.utcnow())
        except:
            return None

    def refresh_market_cache(self, db):
        return self.scan_markets(db)
