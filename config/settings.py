import os
from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv("PORT", 8080))
DB_PATH = os.getenv("DB_PATH", "./data/bot.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
TRADING_MODE = os.getenv("TRADING_MODE", "paper")  # "paper" or "live"
POLYMARKET_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")
POLYMARKET_PASSPHRASE = os.getenv("POLYMARKET_PASSPHRASE", "")

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"
OPENMETEO_BASE = "https://api.open-meteo.com/v1"

TRADE_SCAN_HOURS = "8,14,20"    # UTC
RESOLUTION_CHECK_HOURS = "9,15,21"  # UTC

DEFAULT_SHARES = 100
REDUCED_SHARES = 10
LOSS_THRESHOLD = 2      # >2 losses triggers reduction (i.e., 3 or more)
LOSS_WINDOW_DAYS = 3
MAX_TRADES_PER_MARKET_PER_DAY = 2

STARTING_BALANCE = 10000.0
TEMP_PROXIMITY_C = 2.0   # Within 2°C of forecast triggers Strategy 1
TEMP_PROXIMITY_F = 3.6

API_RETRY_COUNT = 3
API_RETRY_DELAY = 1.0
MARKET_CACHE_TTL_MINUTES = 60
WEATHER_CACHE_TTL_MINUTES = 120
