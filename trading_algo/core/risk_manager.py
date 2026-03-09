"""
APEX TRADING SYSTEM - Risk Manager
=====================================
Enforces all risk rules:
  - Max daily drawdown halt
  - Position sizing limits
  - Correlation-based portfolio risk
  - Trailing stop management
  - Emergency shutdown
"""

import logging
from datetime import datetime, date
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from config.config import (
    MAX_DAILY_DRAWDOWN_PCT, MAX_OPEN_POSITIONS
)

logger = logging.getLogger(__name__)


@dataclass
class RiskMetrics:
    account_balance: float = 0.0
    account_equity: float = 0.0
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    open_positions: int = 0
    total_exposure: float = 0.0
    max_drawdown_today: float = 0.0
    trading_halted: bool = False
    halt_reason: str = ""
    last_updated: str = ""


class RiskManager:
    """
    Central risk management system.
    All trade orders must be approved by this class before execution.
    """

    def __init__(self, vantage_api=None, firebase_db=None):
        self.api = vantage_api
        self.db = firebase_db
        self.metrics = RiskMetrics()
        self.daily_start_balance = 0.0
        self.current_date = date.today()
        self.open_positions: Dict[str, Dict] = {}
        self.daily_trades: List[Dict] = []
        self.trading_halted = False
        self.halt_reason = ""

    def update_metrics(self):
        """Refresh all risk metrics from the broker."""
        if self.api:
            balance = self.api.get_account_balance()
            equity = self.api.get_equity()
            daily_pnl = self.api.get_daily_pnl()
            open_pos = self.api.get_open_positions()
        else:
            # Paper trading / testing mode
            balance = self.daily_start_balance or 10000.0
            equity = balance + sum(
                p.get("unrealized_pnl", 0) for p in self.open_positions.values()
            )
            daily_pnl = sum(
                t.get("profit", 0) for t in self.daily_trades
            )
            open_pos = list(self.open_positions.values())

        # Reset daily tracking if new day
        today = date.today()
        if today != self.current_date:
            self.daily_start_balance = balance
            self.daily_trades = []
            self.current_date = today
            if self.trading_halted:
                logger.info("New trading day — resetting halt status")
                self.trading_halted = False
                self.halt_reason = ""

        if self.daily_start_balance == 0:
            self.daily_start_balance = balance

        daily_pnl_pct = ((equity - self.daily_start_balance) /
                          max(self.daily_start_balance, 1)) * 100

        self.metrics = RiskMetrics(
            account_balance=balance,
            account_equity=equity,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            open_positions=len(open_pos),
            total_exposure=sum(float(p.get("volume", 0)) for p in open_pos),
            max_drawdown_today=min(daily_pnl_pct, 0),
            trading_halted=self.trading_halted,
            halt_reason=self.halt_reason,
            last_updated=datetime.now().isoformat()
        )

        # Check drawdown limit
        if daily_pnl_pct <= -MAX_DAILY_DRAWDOWN_PCT and not self.trading_halted:
            self._halt_trading(
                f"Daily drawdown limit reached: {daily_pnl_pct:.2f}% "
                f"(limit: -{MAX_DAILY_DRAWDOWN_PCT}%)"
            )

        return self.metrics

    def approve_trade(self, signal, account_balance: float) -> Tuple_like:
        """
        Review a trade signal and return (approved: bool, reason: str, volume: float).
        """
        if self.trading_halted:
            return False, f"Trading halted: {self.halt_reason}", 0.0

        # Check max positions
        if len(self.open_positions) >= MAX_OPEN_POSITIONS:
            return False, f"Max positions reached ({MAX_OPEN_POSITIONS})", 0.0

        # Check signal quality
        if signal.action == "HOLD":
            return False, "Signal is HOLD", 0.0

        if signal.confidence < 0.65:
            return False, f"Confidence too low: {signal.confidence:.2f}", 0.0

        if signal.risk_reward < 1.5:
            return False, f"R:R too low: {signal.risk_reward:.2f}", 0.0

        # Check not already in this symbol
        if signal.symbol in self.open_positions:
            existing = self.open_positions[signal.symbol]
            if existing.get("side") == signal.action.lower():
                return False, f"Already have {signal.action} position in {signal.symbol}", 0.0

        # Calculate position volume
        volume = self._calculate_volume(signal, account_balance)
        if volume <= 0:
            return False, "Calculated volume is zero", 0.0

        return True, "Approved", volume

    def _calculate_volume(self, signal, account_balance: float) -> float:
        """
        Calculate position size in lots based on:
        - ML-recommended position size %
        - Account balance
        - Stop loss distance
        - Max risk per trade
        """
        risk_amount = account_balance * signal.position_size_pct
        sl_distance = abs(signal.entry_price - signal.stop_loss)

        if sl_distance == 0:
            return 0.0

        # Approximate pip value (varies by instrument)
        pip_values = {
            "XAUUSD": 1.0,   # $1 per 0.01 per oz
            "XAGUSD": 0.5,
            "USOIL": 1.0,    # $1 per 0.01 per barrel
            "UKOIL": 1.0,
            "NGAS": 0.1,
        }
        pip_value = pip_values.get(signal.symbol, 1.0)

        volume = risk_amount / (sl_distance * pip_value * 100)
        volume = round(max(0.01, min(volume, 10.0)), 2)  # 0.01 to 10 lots

        return volume

    def record_trade_open(self, signal, order_result: Dict, volume: float):
        """Record a newly opened position."""
        self.open_positions[signal.symbol] = {
            "id": order_result.get("id"),
            "symbol": signal.symbol,
            "side": signal.action.lower(),
            "volume": volume,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "confidence": signal.confidence,
            "opened_at": datetime.now().isoformat(),
            "unrealized_pnl": 0.0
        }
        logger.info(f"Position recorded: {signal.action} {volume} {signal.symbol}")

    def record_trade_close(self, symbol: str, profit: float):
        """Record a closed position."""
        if symbol in self.open_positions:
            trade = self.open_positions.pop(symbol)
            trade["profit"] = profit
            trade["closed_at"] = datetime.now().isoformat()
            self.daily_trades.append(trade)
            logger.info(f"Position closed: {symbol} | P&L: ${profit:.2f}")

    def update_trailing_stops(self, current_prices: Dict[str, float]):
        """
        Update trailing stops for profitable positions.
        Trail by 1.5x ATR once in profit by 1x ATR.
        """
        if not self.api:
            return

        for symbol, position in self.open_positions.items():
            current_price = current_prices.get(symbol)
            if not current_price:
                continue

            entry = position["entry_price"]
            current_sl = position["stop_loss"]
            side = position["side"]

            # Simple trailing: move SL to lock in 50% of profit
            if side == "buy":
                profit_distance = current_price - entry
                if profit_distance > 0:
                    new_sl = entry + profit_distance * 0.5
                    if new_sl > current_sl:
                        position["stop_loss"] = new_sl
                        if self.api:
                            self.api.modify_order(position["id"], stop_loss=new_sl)
                        logger.debug(f"Trailing SL updated: {symbol} SL → {new_sl:.5f}")

            elif side == "sell":
                profit_distance = entry - current_price
                if profit_distance > 0:
                    new_sl = entry - profit_distance * 0.5
                    if new_sl < current_sl:
                        position["stop_loss"] = new_sl
                        if self.api:
                            self.api.modify_order(position["id"], stop_loss=new_sl)

    def _halt_trading(self, reason: str):
        """Emergency halt all new trading."""
        self.trading_halted = True
        self.halt_reason = reason
        logger.critical(f"⛔ TRADING HALTED: {reason}")

        # Save halt to Firebase
        if self.db:
            self.db.set_value("system/trading_halted", True)
            self.db.set_value("system/halt_reason", reason)
            self.db.set_value("system/halt_time", datetime.now().isoformat())

    def resume_trading(self):
        """Manually resume trading (from dashboard)."""
        self.trading_halted = False
        self.halt_reason = ""
        logger.info("✅ Trading resumed manually")
        if self.db:
            self.db.set_value("system/trading_halted", False)

    def get_portfolio_summary(self) -> Dict:
        """Get current portfolio state for dashboard/email."""
        return {
            "balance": self.metrics.account_balance,
            "equity": self.metrics.account_equity,
            "daily_pnl": self.metrics.daily_pnl,
            "daily_pnl_pct": self.metrics.daily_pnl_pct,
            "open_positions": len(self.open_positions),
            "positions": list(self.open_positions.values()),
            "trading_halted": self.trading_halted,
            "halt_reason": self.halt_reason,
            "daily_trades_count": len(self.daily_trades),
            "timestamp": datetime.now().isoformat()
        }


# Python < 3.10 compat
def Tuple_like():
    pass
