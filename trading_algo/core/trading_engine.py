"""
APEX TRADING SYSTEM - Core Trading Engine
==========================================
Orchestrates the full trading loop:
  1. Fetch market data
  2. Run ML models → generate signals
  3. Risk check → approve/reject trades
  4. Execute via Vantage API
  5. Sync to Firebase
  6. Send email reports
  7. Retrain ML models periodically
"""

import sys
import time
import logging
import schedule
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

from config.config import (
    ALL_MARKETS, PRIMARY_MARKETS, TRADING_MODE,
    ML_RETRAIN_INTERVAL_HOURS, DAILY_REPORT_TIME,
    WEEKLY_REPORT_DAY, LOG_FILE, LOG_LEVEL
)

# Setup logging
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("APEX")


class ApexTradingEngine:
    """
    Master trading engine that runs the full trading loop.
    """

    def __init__(self, mode: str = None):
        self.mode = mode or TRADING_MODE
        self.running = False
        self.paused = False
        self.status = "initializing"
        self.last_cycle_time = None
        self.cycle_count = 0
        self.stats = {
            "signals_generated": 0,
            "trades_executed": 0,
            "trades_rejected": 0,
            "errors": 0
        }

        logger.info("=" * 60)
        logger.info(f"  ⚡ APEX TRADING SYSTEM STARTING — MODE: {self.mode.upper()}")
        logger.info("=" * 60)

        self._initialize_components()
        self._schedule_tasks()

    def _initialize_components(self):
        """Initialize all system components."""
        logger.info("Initializing components...")

        # API
        from core.vantage_api import VantageAPI
        self.api = VantageAPI(mode=self.mode)

        # Data
        from data.data_fetcher import DataFetcher
        self.data = DataFetcher(vantage_api=self.api)

        # ML
        from ml.ml_engine import MLEngine
        self.ml = MLEngine()

        # Firebase
        from firebase.firebase_db import FirebaseDB
        self.db = FirebaseDB()

        # Risk
        from core.risk_manager import RiskManager
        self.risk = RiskManager(vantage_api=self.api, firebase_db=self.db)

        # Email
        from email_reports.email_reporter import EmailReporter
        self.email = EmailReporter()

        # State
        self.current_prices: Dict[str, float] = {}
        self.last_signals: Dict = {}
        self.last_retrain = datetime.now() - timedelta(hours=ML_RETRAIN_INTERVAL_HOURS)

        logger.info("✅ All components initialized")
        self.db.log_system_event("startup", f"APEX started in {self.mode} mode")

    def _schedule_tasks(self):
        """Schedule periodic tasks."""
        # Daily report
        schedule.every().day.at(DAILY_REPORT_TIME).do(self._send_daily_report)

        # Weekly report
        getattr(schedule.every(), WEEKLY_REPORT_DAY.lower()).at("18:30").do(
            self._send_weekly_report
        )

        # ML retrain
        schedule.every(ML_RETRAIN_INTERVAL_HOURS).hours.do(self._retrain_all_models)

        # Trailing stop updates
        schedule.every(5).minutes.do(self._update_trailing_stops)

        # Firebase sync
        schedule.every(30).seconds.do(self._sync_to_firebase)

        logger.info("✅ Scheduled tasks configured")

    # ─────────────────────────────────────────────
    # MAIN LOOP
    # ─────────────────────────────────────────────

    def start(self):
        """Start the trading engine main loop."""
        self.running = True
        self.status = "running"
        logger.info(f"🚀 Trading engine started | Mode: {self.mode.upper()}")

        # Initial model training if no saved models
        if not self.ml.models:
            logger.info("No saved models found — training initial models...")
            self._retrain_all_models()

        # Run scheduler in background thread
        scheduler_thread = threading.Thread(
            target=self._run_scheduler, daemon=True
        )
        scheduler_thread.start()

        # Main trading loop
        while self.running:
            try:
                if not self.paused:
                    self._trading_cycle()
                time.sleep(60)  # 1-minute cycle

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                self.stop()
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)
                self.stats["errors"] += 1
                self.db.log_system_event("error", str(e))
                time.sleep(30)

    def _trading_cycle(self):
        """Single iteration of the trading loop."""
        cycle_start = datetime.now()
        self.cycle_count += 1

        logger.debug(f"Trading cycle #{self.cycle_count}")

        # 1. Update risk metrics
        self.risk.update_metrics()
        if self.risk.trading_halted:
            logger.warning(f"Trading halted: {self.risk.halt_reason}")
            return

        # 2. Update current prices
        self._update_prices()

        # 3. Check existing positions (exit conditions)
        self._check_exit_conditions()

        # 4. Generate signals for all markets
        signals = self._generate_all_signals()

        # 5. Execute approved trades
        for signal in signals:
            if signal.action != "HOLD":
                self._process_signal(signal)

        self.last_cycle_time = datetime.now()
        cycle_ms = (self.last_cycle_time - cycle_start).total_seconds() * 1000
        logger.debug(f"Cycle #{self.cycle_count} completed in {cycle_ms:.0f}ms")

    def _update_prices(self):
        """Fetch current prices for all active markets."""
        symbols = list(ALL_MARKETS.keys())
        try:
            bulk = self.api.get_prices_bulk(symbols)
            if bulk:
                for symbol in symbols:
                    price_data = bulk.get(symbol, {})
                    if price_data:
                        self.current_prices[symbol] = float(
                            price_data.get("ask", price_data.get("price", 0))
                        )
        except Exception as e:
            logger.warning(f"Price update failed: {e}")

    def _generate_all_signals(self) -> list:
        """Generate ML signals for all markets."""
        signals = []

        # Focus on primary markets first
        markets = list(PRIMARY_MARKETS.keys())
        if len(self.risk.open_positions) < 6:
            markets += list(set(ALL_MARKETS.keys()) - set(markets))

        for symbol in markets:
            try:
                # Get OHLCV data
                df = self.data.get_ohlcv_df(symbol, timeframe="1h", periods=500)
                if df is None or len(df) < 50:
                    continue

                current_price = self.current_prices.get(symbol)
                if not current_price:
                    current_price = float(df["close"].iloc[-1])

                # Get fundamental features for energy markets
                fund_features = {}
                if ALL_MARKETS[symbol]["category"] == "energy":
                    eia = self.data.get_eia_oil_inventories()
                    fund_features.update(eia)
                    cal = self.data.get_economic_calendar_features()
                    fund_features.update(cal)

                # Generate ML signal
                signal = self.ml.generate_signal(
                    symbol=symbol,
                    df=df,
                    current_price=current_price,
                    fundamental_features=fund_features,
                    account_balance=self.risk.metrics.account_balance
                )

                self.last_signals[symbol] = signal
                self.stats["signals_generated"] += 1

                if signal.action != "HOLD":
                    logger.info(
                        f"Signal: {signal.action} {symbol} | "
                        f"Confidence: {signal.confidence:.1%} | "
                        f"R:R: {signal.risk_reward:.1f} | "
                        f"Regime: {signal.regime}"
                    )
                    signals.append(signal)

                # Log to Firebase
                self.db.log_signal(signal)

            except Exception as e:
                logger.error(f"Signal error for {symbol}: {e}")
                self.stats["errors"] += 1

        return signals

    def _process_signal(self, signal):
        """Run risk checks and execute a trade signal."""
        balance = self.risk.metrics.account_balance or 10000.0
        approved, reason, volume = self.risk.approve_trade(signal, balance)

        if not approved:
            logger.debug(f"Trade rejected [{signal.symbol}]: {reason}")
            self.stats["trades_rejected"] += 1
            return

        # Place order
        order = self.api.place_order(
            symbol=signal.symbol,
            side=signal.action.lower(),
            order_type="market",
            volume=volume,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            comment=f"APEX_{signal.strategy_used[:10]}"
        )

        if order:
            self.risk.record_trade_open(signal, order, volume)
            self.stats["trades_executed"] += 1
            logger.info(
                f"✅ Trade executed: {signal.action} {volume} {signal.symbol} @ "
                f"{signal.entry_price:.4f} | SL:{signal.stop_loss:.4f} "
                f"TP:{signal.take_profit:.4f}"
            )

            # Alert for significant trades
            if volume * signal.entry_price > balance * 0.03:
                self.email.send_alert(
                    "info",
                    f"New trade: {signal.action} {volume} {signal.symbol}",
                    {
                        "Entry": f"${signal.entry_price:.4f}",
                        "Stop Loss": f"${signal.stop_loss:.4f}",
                        "Take Profit": f"${signal.take_profit:.4f}",
                        "Confidence": f"{signal.confidence:.1%}",
                        "R:R": f"{signal.risk_reward:.1f}x",
                        "Mode": self.mode.upper()
                    }
                )
        else:
            logger.error(f"Order failed for {signal.symbol}")
            self.stats["errors"] += 1

    def _check_exit_conditions(self):
        """Check if any open positions should be manually exited."""
        for symbol, position in list(self.risk.open_positions.items()):
            try:
                current_price = self.current_prices.get(symbol)
                if not current_price:
                    continue

                side = position.get("side")
                entry = position.get("entry_price", 0)
                tp = position.get("take_profit", 0)
                sl = position.get("stop_loss", 0)

                # Check if SL or TP hit (broker handles this, but verify)
                if side == "buy":
                    pnl = (current_price - entry) / entry
                    if current_price <= sl or current_price >= tp:
                        profit = (current_price - entry) * position.get("volume", 0)
                        self.api.close_position(position["id"])
                        self.risk.record_trade_close(symbol, profit)
                elif side == "sell":
                    if current_price >= sl or current_price <= tp:
                        profit = (entry - current_price) * position.get("volume", 0)
                        self.api.close_position(position["id"])
                        self.risk.record_trade_close(symbol, profit)

            except Exception as e:
                logger.error(f"Exit check error for {symbol}: {e}")

    # ─────────────────────────────────────────────
    # SCHEDULED TASKS
    # ─────────────────────────────────────────────

    def _retrain_all_models(self):
        """Retrain ML models for all markets with latest data."""
        logger.info("🔄 Starting ML model retraining...")
        for symbol in list(ALL_MARKETS.keys()):
            try:
                df = self.data.get_ohlcv_df(
                    symbol, timeframe="1h", periods=2000
                )
                if df is not None and len(df) > 200:
                    fund_features = {}
                    if ALL_MARKETS[symbol]["category"] == "energy":
                        fund_features = self.data.get_eia_oil_inventories()

                    metrics = self.ml.train(symbol, df, fund_features)
                    if metrics:
                        self.db.update_ml_metrics(symbol, metrics)
                        logger.info(f"✅ {symbol} model retrained")
            except Exception as e:
                logger.error(f"Retraining error for {symbol}: {e}")

        self.last_retrain = datetime.now()
        logger.info("✅ ML retraining complete")

    def _update_trailing_stops(self):
        """Update trailing stops for all open positions."""
        self.risk.update_trailing_stops(self.current_prices)

    def _sync_to_firebase(self):
        """Push portfolio snapshot to Firebase."""
        try:
            snapshot = self.risk.get_portfolio_summary()
            snapshot["mode"] = self.mode
            snapshot["cycle_count"] = self.cycle_count
            snapshot["stats"] = self.stats
            self.db.update_portfolio_snapshot(snapshot)
        except Exception as e:
            logger.error(f"Firebase sync error: {e}")

    def _send_daily_report(self):
        """Compile and send daily P&L email."""
        logger.info("Sending daily report...")
        try:
            portfolio = self.risk.get_portfolio_summary()
            trades = self.risk.daily_trades

            # Get news highlights
            sentiment = self.data.get_news_sentiment(list(PRIMARY_MARKETS.keys()))
            news_highlights = [
                f"{symbol}: {'Bullish' if s > 0.1 else 'Bearish' if s < -0.1 else 'Neutral'} "
                f"sentiment ({s:+.2f})"
                for symbol, s in sentiment.items()
            ]

            self.email.send_daily_report(portfolio, trades, news_highlights=news_highlights)

            # Save to Firebase
            date_str = datetime.now().strftime("%Y-%m-%d")
            self.db.save_daily_report(date_str, {
                **portfolio,
                "trade_count": len(trades)
            })
            self.db.update_daily_pnl(date_str, {
                "pnl": portfolio["daily_pnl"],
                "pnl_pct": portfolio["daily_pnl_pct"],
                "trades": len(trades),
                "equity": portfolio["account_equity"]
            })

        except Exception as e:
            logger.error(f"Daily report error: {e}")

    def _send_weekly_report(self):
        """Compile and send weekly performance email."""
        logger.info("Sending weekly report...")
        try:
            all_trades = self.risk.daily_trades
            total_pnl = sum(t.get("profit", 0) for t in all_trades)
            wins = [t for t in all_trades if t.get("profit", 0) > 0]
            win_rate = len(wins) / max(len(all_trades), 1)

            by_market = {}
            for t in all_trades:
                sym = t.get("symbol", "?")
                if sym not in by_market:
                    by_market[sym] = {"symbol": sym, "trades": 0, "pnl": 0, "wins": 0}
                by_market[sym]["trades"] += 1
                by_market[sym]["pnl"] += t.get("profit", 0)
                if t.get("profit", 0) > 0:
                    by_market[sym]["wins"] += 1
            for sym in by_market:
                by_market[sym]["win_rate"] = (
                    by_market[sym]["wins"] / max(by_market[sym]["trades"], 1)
                )

            balance = self.risk.metrics.account_balance or 10000
            weekly_stats = {
                "total_pnl": total_pnl,
                "pnl_pct": (total_pnl / max(balance, 1)) * 100,
                "total_trades": len(all_trades),
                "win_rate": win_rate,
                "best_trade": max((t.get("profit", 0) for t in all_trades), default=0),
                "avg_rr": 2.0,
                "by_market": sorted(
                    by_market.values(), key=lambda x: x["pnl"], reverse=True
                )[:5]
            }

            self.email.send_weekly_report(weekly_stats, [])

        except Exception as e:
            logger.error(f"Weekly report error: {e}")

    def _run_scheduler(self):
        """Run the schedule loop in background thread."""
        while self.running:
            schedule.run_pending()
            time.sleep(1)

    # ─────────────────────────────────────────────
    # CONTROLS (called from dashboard)
    # ─────────────────────────────────────────────

    def set_mode(self, mode: str):
        """Switch between paper and live trading."""
        if mode not in ["paper", "live"]:
            return False
        self.mode = mode
        self.api.mode = mode
        logger.info(f"Mode switched to: {mode.upper()}")
        self.db.log_system_event("mode_change", f"Switched to {mode} mode")
        return True

    def pause(self):
        self.paused = True
        self.status = "paused"
        logger.info("Trading engine paused")

    def resume(self):
        self.paused = False
        self.status = "running"
        logger.info("Trading engine resumed")

    def stop(self):
        self.running = False
        self.status = "stopped"
        logger.info("⛔ Trading engine stopped")
        self.db.log_system_event("shutdown", "APEX trading engine stopped")

    def get_status(self) -> Dict:
        return {
            "status": self.status,
            "mode": self.mode,
            "paused": self.paused,
            "cycle_count": self.cycle_count,
            "last_cycle": self.last_cycle_time.isoformat() if self.last_cycle_time else None,
            "last_retrain": self.last_retrain.isoformat(),
            "stats": self.stats,
            "risk": {
                "halted": self.risk.trading_halted,
                "halt_reason": self.risk.halt_reason,
                "daily_pnl_pct": self.risk.metrics.daily_pnl_pct,
                "open_positions": len(self.risk.open_positions)
            }
        }
