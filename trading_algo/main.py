#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║    ⚡  APEX TRADING SYSTEM  ⚡                               ║
║                                                              ║
║    Automated ML-powered commodity trading                    ║
║    Gold · Silver · Crude Oil · Natural Gas · Low Carbon      ║
║                                                              ║
║    Usage:                                                    ║
║      python main.py              → Launch full system        ║
║      python main.py --dashboard  → Dashboard only (demo)     ║
║      python main.py --engine     → Engine only (headless)    ║
║      python main.py --train      → Train models only         ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
import argparse
import threading
import logging

logger = logging.getLogger("APEX.Main")


def run_full_system():
    """Launch trading engine + dashboard together."""
    print("\n⚡ Starting APEX Trading System...\n")

    # Start engine in background thread
    from core.trading_engine import ApexTradingEngine
    engine = ApexTradingEngine()

    engine_thread = threading.Thread(
        target=engine.start,
        daemon=True,
        name="TradingEngine"
    )
    engine_thread.start()

    # Launch dashboard (blocks main thread)
    from dashboard.dashboard import launch_dashboard
    launch_dashboard(engine=engine)


def run_dashboard_only():
    """Launch dashboard in demo mode (no live engine)."""
    print("\n⚡ Starting APEX Dashboard (Demo Mode)...\n")
    from dashboard.dashboard import launch_dashboard
    launch_dashboard(engine=None)


def run_engine_only():
    """Run the trading engine headless (no GUI)."""
    print("\n⚡ Starting APEX Engine (Headless)...\n")
    from core.trading_engine import ApexTradingEngine
    engine = ApexTradingEngine()
    engine.start()  # Blocks main thread


def run_training_only():
    """Train/retrain all ML models and exit."""
    print("\n⚡ Training APEX ML Models...\n")
    from core.vantage_api import VantageAPI
    from data.data_fetcher import DataFetcher
    from ml.ml_engine import MLEngine
    from config.config import ALL_MARKETS

    api = VantageAPI(mode="paper")
    data = DataFetcher(vantage_api=api)
    ml = MLEngine()

    for symbol, info in ALL_MARKETS.items():
        print(f"  Training {symbol} ({info['name']})...")
        df = data.get_ohlcv_df(symbol, timeframe="1h", periods=2000)
        if df is not None and len(df) > 100:
            metrics = ml.train(symbol, df)
            if metrics:
                print(f"    ✅ RF: {metrics.get('rf_cv_accuracy', 0):.1%} | "
                      f"GB: {metrics.get('gb_cv_accuracy', 0):.1%} | "
                      f"XGB: {metrics.get('xgb_cv_accuracy', 0):.1%}")
        else:
            print(f"    ⚠️  Insufficient data for {symbol}")

    print("\n✅ Training complete!\n")


def print_setup_guide():
    """Print setup instructions."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    APEX SETUP GUIDE                         ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. INSTALL DEPENDENCIES:                                    ║
║     pip install -r requirements.txt                          ║
║                                                              ║
║  2. VANTAGE API (vantage REST API):                          ║
║     → Get API key from your Vantage account                  ║
║     → Edit config/config.py:                                 ║
║       VANTAGE_API_KEY = "your_key"                           ║
║       VANTAGE_API_SECRET = "your_secret"                     ║
║       VANTAGE_BASE_URL = "https://api.vantagemarkets.com/v1" ║
║                                                              ║
║  3. FIREBASE (real-time database):                           ║
║     → Go to https://console.firebase.google.com             ║
║     → Create project "apex-trading"                          ║
║     → Enable Realtime Database                               ║
║     → Download service account JSON                          ║
║     → Save as: config/firebase_credentials.json             ║
║     → Update FIREBASE_CONFIG in config/config.py            ║
║                                                              ║
║  4. EMAIL (daily reports):                                   ║
║     → Use a Gmail account                                    ║
║     → Enable 2FA and create an App Password                  ║
║     → Edit config/config.py:                                 ║
║       EMAIL_SENDER = "your@gmail.com"                        ║
║       EMAIL_PASSWORD = "your_app_password"                   ║
║                                                              ║
║  5. OPTIONAL - Better fundamentals data:                     ║
║     → Alpha Vantage (free): alphavantage.co                  ║
║     → EIA Oil Data (free): eia.gov/developer                 ║
║     → News API (free): newsapi.org                           ║
║                                                              ║
║  6. RUN:                                                     ║
║     python main.py                                           ║
║                                                              ║
║  7. START IN PAPER MODE (recommended):                       ║
║     → Set TRADING_MODE = "paper" in config.py               ║
║     → Monitor for 2-4 weeks before going live               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="APEX Automated Trading System"
    )
    parser.add_argument("--dashboard", action="store_true",
                        help="Launch dashboard only (demo mode)")
    parser.add_argument("--engine", action="store_true",
                        help="Run engine headless (no GUI)")
    parser.add_argument("--train", action="store_true",
                        help="Train ML models and exit")
    parser.add_argument("--setup", action="store_true",
                        help="Show setup instructions")

    args = parser.parse_args()

    if args.setup:
        print_setup_guide()
    elif args.dashboard:
        run_dashboard_only()
    elif args.engine:
        run_engine_only()
    elif args.train:
        run_training_only()
    else:
        run_full_system()
