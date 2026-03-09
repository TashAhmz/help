"""
APEX TRADING SYSTEM - Configuration
=====================================
Edit this file to configure your trading system.
"""

# ─────────────────────────────────────────────
# VANTAGE API CREDENTIALS (fill in when ready)
# ─────────────────────────────────────────────
VANTAGE_API_KEY = "YOUR_VANTAGE_API_KEY"
VANTAGE_API_SECRET = "YOUR_VANTAGE_API_SECRET"
VANTAGE_BASE_URL = "https://api.vantagemarkets.com/v1"  # Update with real endpoint

# ─────────────────────────────────────────────
# FIREBASE CREDENTIALS (fill in after setup)
# ─────────────────────────────────────────────
FIREBASE_CONFIG = {
    "apiKey": "YOUR_FIREBASE_API_KEY",
    "authDomain": "YOUR_PROJECT.firebaseapp.com",
    "databaseURL": "https://YOUR_PROJECT-default-rtdb.firebaseio.com",
    "projectId": "YOUR_PROJECT_ID",
    "storageBucket": "YOUR_PROJECT.appspot.com",
    "messagingSenderId": "YOUR_SENDER_ID",
    "appId": "YOUR_APP_ID"
}
FIREBASE_CREDENTIALS_PATH = "config/firebase_credentials.json"

# ─────────────────────────────────────────────
# EMAIL CONFIGURATION
# ─────────────────────────────────────────────
EMAIL_RECIPIENTS = [
    "Josephhyland10@icloud.com",
    "tashifkarim@gmail.com"
]
EMAIL_SENDER = "trading.apex.bot@gmail.com"
EMAIL_PASSWORD = "YOUR_EMAIL_APP_PASSWORD"  # Gmail app password
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# ─────────────────────────────────────────────
# MARKETS TO TRADE
# ─────────────────────────────────────────────
PRIMARY_MARKETS = {
    # Precious Metals
    "XAUUSD": {"name": "Gold / USD",        "category": "metals",    "priority": 1},
    "XAGUSD": {"name": "Silver / USD",       "category": "metals",    "priority": 2},

    # Energy - PRIMARY FOCUS
    "USOIL":  {"name": "Crude Oil (WTI)",    "category": "energy",    "priority": 1},
    "UKOIL":  {"name": "Crude Oil (Brent)",  "category": "energy",    "priority": 1},
    "NGAS":   {"name": "Natural Gas",        "category": "energy",    "priority": 2},
    "HEAT":   {"name": "Heating Oil",        "category": "energy",    "priority": 2},
    "RBOB":   {"name": "RBOB Gasoline",      "category": "energy",    "priority": 2},
}

SECONDARY_MARKETS = {
    # Low Carbon / Clean Energy (secondary focus)
    "ETHUSD": {"name": "Ethanol (proxy)",    "category": "low_carbon", "priority": 3},
    "CARBON": {"name": "Carbon Credits",     "category": "low_carbon", "priority": 3},
}

ALL_MARKETS = {**PRIMARY_MARKETS, **SECONDARY_MARKETS}

# ─────────────────────────────────────────────
# TRADING PARAMETERS
# ─────────────────────────────────────────────
TRADING_MODE = "paper"          # "paper" or "live" — switch via dashboard
MAX_DAILY_DRAWDOWN_PCT = 5.0    # Halt all trading if daily loss exceeds this %
MAX_OPEN_POSITIONS = 8          # Max simultaneous open trades
ML_RETRAIN_INTERVAL_HOURS = 24  # How often to retrain ML models
MIN_ML_CONFIDENCE = 0.65        # Minimum ML confidence to place a trade (0-1)
LOOKBACK_PERIOD_DAYS = 365      # Historical data for ML training

# ─────────────────────────────────────────────
# FUNDAMENTAL DATA SOURCES (free APIs)
# ─────────────────────────────────────────────
ALPHA_VANTAGE_KEY = "YOUR_ALPHA_VANTAGE_KEY"  # Free at alphavantage.co
EIA_API_KEY = "YOUR_EIA_API_KEY"              # Free at eia.gov (oil inventory data)
NEWS_API_KEY = "YOUR_NEWS_API_KEY"            # Free at newsapi.org

# ─────────────────────────────────────────────
# SYSTEM
# ─────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FILE = "logs/apex_trading.log"
DATA_DIR = "data/"
MODEL_DIR = "ml/models/"
DASHBOARD_PORT = 8080
DAILY_REPORT_TIME = "18:00"   # Send daily P&L email at 6pm
WEEKLY_REPORT_DAY = "Friday"  # Send weekly summary on Friday
