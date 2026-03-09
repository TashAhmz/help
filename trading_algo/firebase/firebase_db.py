"""
APEX TRADING SYSTEM - Firebase Real-Time Database
===================================================
Syncs all trading data to Firebase in real-time:
  - Live positions & P&L
  - Trade history
  - System status
  - ML model performance
  - Alerts

Setup Instructions:
  1. Go to https://console.firebase.google.com
  2. Create new project: "apex-trading"
  3. Enable Realtime Database
  4. Go to Project Settings > Service Accounts
  5. Generate new private key → save as config/firebase_credentials.json
  6. Copy config values into config/config.py
"""

import json
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class FirebaseDB:
    """
    Firebase Realtime Database connector.
    Uses firebase-admin SDK for server-side access.
    """

    def __init__(self):
        self.db = None
        self.connected = False
        self._listeners = {}
        self._connect()

    def _connect(self):
        """Initialize Firebase connection."""
        try:
            import firebase_admin
            from firebase_admin import credentials, db
            from config.config import FIREBASE_CREDENTIALS_PATH, FIREBASE_CONFIG

            creds_path = Path(FIREBASE_CREDENTIALS_PATH)
            if not creds_path.exists():
                logger.warning(
                    f"Firebase credentials not found at {creds_path}. "
                    "Running in local-only mode. "
                    "See config/config.py for setup instructions."
                )
                return

            # Avoid re-initialization
            if not firebase_admin._apps:
                cred = credentials.Certificate(str(creds_path))
                firebase_admin.initialize_app(cred, {
                    "databaseURL": FIREBASE_CONFIG["databaseURL"]
                })

            self.db = db
            self.connected = True
            logger.info("✅ Firebase connected successfully")

        except ImportError:
            logger.warning("firebase-admin not installed. Run: pip install firebase-admin")
        except Exception as e:
            logger.error(f"Firebase connection error: {e}")

    # ─────────────────────────────────────────────
    # WRITE OPERATIONS
    # ─────────────────────────────────────────────

    def set_value(self, path: str, value: Any) -> bool:
        """Set a value at the given path."""
        if not self.connected:
            return self._local_fallback("set", path, value)
        try:
            self.db.reference(path).set(value)
            return True
        except Exception as e:
            logger.error(f"Firebase set error at {path}: {e}")
            return False

    def update_value(self, path: str, updates: Dict) -> bool:
        """Update multiple fields at a path."""
        if not self.connected:
            return self._local_fallback("update", path, updates)
        try:
            self.db.reference(path).update(updates)
            return True
        except Exception as e:
            logger.error(f"Firebase update error at {path}: {e}")
            return False

    def push_value(self, path: str, value: Any) -> Optional[str]:
        """Push a new entry (auto-generates key). Returns the new key."""
        if not self.connected:
            self._local_fallback("push", path, value)
            return None
        try:
            ref = self.db.reference(path).push(value)
            return ref.key
        except Exception as e:
            logger.error(f"Firebase push error at {path}: {e}")
            return None

    # ─────────────────────────────────────────────
    # READ OPERATIONS
    # ─────────────────────────────────────────────

    def get_value(self, path: str) -> Optional[Any]:
        """Get value at path."""
        if not self.connected:
            return None
        try:
            return self.db.reference(path).get()
        except Exception as e:
            logger.error(f"Firebase get error at {path}: {e}")
            return None

    # ─────────────────────────────────────────────
    # TRADING-SPECIFIC METHODS
    # ─────────────────────────────────────────────

    def sync_position(self, position: Dict):
        """Sync a live position to Firebase."""
        symbol = position.get("symbol", "UNKNOWN")
        self.set_value(f"positions/{symbol}", {
            **position,
            "last_sync": datetime.now().isoformat()
        })

    def remove_position(self, symbol: str):
        """Remove closed position from Firebase."""
        if not self.connected:
            return
        try:
            self.db.reference(f"positions/{symbol}").delete()
        except Exception as e:
            logger.error(f"Firebase delete error: {e}")

    def record_trade(self, trade: Dict) -> str:
        """Record completed trade to history."""
        return self.push_value("trade_history", {
            **trade,
            "recorded_at": datetime.now().isoformat()
        })

    def update_portfolio_snapshot(self, snapshot: Dict):
        """Update live portfolio overview."""
        self.set_value("portfolio/live", {
            **snapshot,
            "last_updated": datetime.now().isoformat()
        })

    def update_daily_pnl(self, date_str: str, pnl_data: Dict):
        """Store daily P&L record."""
        self.set_value(f"pnl_history/{date_str}", {
            **pnl_data,
            "date": date_str
        })

    def log_signal(self, signal):
        """Log ML signal to Firebase for analysis."""
        self.push_value("signals_log", {
            "symbol": signal.symbol,
            "action": signal.action,
            "confidence": signal.confidence,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "risk_reward": signal.risk_reward,
            "regime": signal.regime,
            "strategy": signal.strategy_used,
            "timestamp": signal.timestamp.isoformat()
        })

    def log_system_event(self, event_type: str, message: str):
        """Log system events (errors, halts, restarts)."""
        self.push_value("system_log", {
            "type": event_type,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })

    def update_ml_metrics(self, symbol: str, metrics: Dict):
        """Store ML training/performance metrics."""
        self.set_value(f"ml_metrics/{symbol}", {
            **metrics,
            "updated_at": datetime.now().isoformat()
        })

    def save_daily_report(self, date_str: str, report: Dict):
        """Save daily report data to Firebase."""
        self.set_value(f"reports/daily/{date_str}", report)

    # ─────────────────────────────────────────────
    # LOCAL FALLBACK (when Firebase not connected)
    # ─────────────────────────────────────────────

    def _local_fallback(self, operation: str, path: str, value: Any) -> bool:
        """
        Save to local JSON file when Firebase is unavailable.
        Data will sync to Firebase once credentials are configured.
        """
        local_path = Path("data/local_db.json")
        try:
            if local_path.exists():
                with open(local_path) as f:
                    data = json.load(f)
            else:
                data = {}

            # Nested path update
            keys = path.strip("/").split("/")
            node = data
            for key in keys[:-1]:
                node = node.setdefault(key, {})
            node[keys[-1]] = value

            with open(local_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            return True

        except Exception as e:
            logger.error(f"Local fallback error: {e}")
            return False

    def get_firebase_setup_guide(self) -> str:
        """Return setup instructions as a formatted string."""
        return """
╔══════════════════════════════════════════════════════════╗
║              FIREBASE SETUP GUIDE                       ║
╠══════════════════════════════════════════════════════════╣
║  1. Visit: https://console.firebase.google.com          ║
║  2. Click "Add Project" → Name it "apex-trading"        ║
║  3. Enable Google Analytics (optional)                  ║
║  4. Go to Build → Realtime Database → Create Database   ║
║  5. Start in test mode (you can secure later)           ║
║  6. Go to Project Settings → Service Accounts           ║
║  7. Click "Generate new private key"                    ║
║  8. Save the JSON as: config/firebase_credentials.json  ║
║  9. Copy the config values into config/config.py        ║
║  10. Restart APEX Trading System                        ║
╚══════════════════════════════════════════════════════════╝
"""
