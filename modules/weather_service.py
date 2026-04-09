import logging
import requests
from datetime import date, timedelta
from typing import Optional
from config.settings import OPENMETEO_BASE, WEATHER_CACHE_TTL_MINUTES
from config.cities import get_city_coords
import time

logger = logging.getLogger(__name__)


class WeatherService:
    def __init__(self):
        self.cache = {}

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid."""
        if cache_key not in self.cache:
            return False
        timestamp, _ = self.cache[cache_key]
        age_minutes = (time.time() - timestamp) / 60
        return age_minutes < WEATHER_CACHE_TTL_MINUTES

    def get_forecast(self, city: str, target_date: date) -> Optional[dict]:
        """
        Get weather forecast for a city on a target date.
        Returns: {"high_temp_c": float, "high_temp_f": float, "city": city, "date": target_date}
        """
        coords = get_city_coords(city)
        if not coords:
            logger.warning(f"City coordinates not found: {city}")
            return None

        cache_key = f"{city}_{target_date}"
        if self._is_cache_valid(cache_key):
            _, forecast = self.cache[cache_key]
            return forecast

        try:
            lat = coords["lat"]
            lon = coords["lon"]

            url = f"{OPENMETEO_BASE}/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&forecast_days=3&timezone=UTC"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            daily_temps = data.get("daily", {}).get("temperature_2m_max", [])
            dates = data.get("daily", {}).get("time", [])

            if not daily_temps or not dates:
                logger.warning(f"No temperature data for {city}")
                return None

            today = date.today()
            for i, date_str in enumerate(dates):
                current_date = date.fromisoformat(date_str)
                if current_date == target_date:
                    temp_c = float(daily_temps[i])
                    temp_f = temp_c * 9 / 5 + 32
                    forecast = {
                        "high_temp_c": temp_c,
                        "high_temp_f": temp_f,
                        "city": city,
                        "date": target_date
                    }
                    self.cache[cache_key] = (time.time(), forecast)
                    logger.debug(f"Weather forecast for {city} on {target_date}: {temp_c}°C")
                    return forecast

            logger.warning(f"No forecast data found for {city} on {target_date}")
            return None

        except Exception as e:
            logger.error(f"Error fetching weather forecast: {e}")
            return None

    def get_forecast_high_c(self, city: str, target_date: date) -> Optional[float]:
        """Get forecast high temperature in Celsius."""
        forecast = self.get_forecast(city, target_date)
        if forecast:
            return forecast["high_temp_c"]
        return None

    def get_forecast_high_f(self, city: str, target_date: date) -> Optional[float]:
        """Get forecast high temperature in Fahrenheit."""
        forecast = self.get_forecast(city, target_date)
        if forecast:
            return forecast["high_temp_f"]
        return None

    def clear_cache(self):
        """Clear all cached forecasts."""
        self.cache.clear()
        logger.info("Weather forecast cache cleared")
