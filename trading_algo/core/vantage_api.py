"""
APEX TRADING SYSTEM - Vantage REST API Connector
=================================================
Handles all communication with the Vantage Markets REST API.
Includes rate limiting, error handling, and retry logic.
"""

import time
import hmac
import hashlib
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from config.config import VANTAGE_API_KEY, VANTAGE_API_SECRET, VANTAGE_BASE_URL

logger = logging.getLogger(__name__)


class VantageAPI:
    """
    Full Vantage Markets REST API wrapper.
    Supports paper and live trading modes.
    """

    def __init__(self, mode: str = "paper"):
        self.api_key = VANTAGE_API_KEY
        self.api_secret = VANTAGE_API_SECRET
        self.base_url = VANTAGE_BASE_URL
        self.mode = mode
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        self._last_request_time = 0
        self._rate_limit_delay = 0.2  # 200ms between requests
        logger.info(f"VantageAPI initialized in {mode.upper()} mode")

    def _sign_request(self, endpoint: str, params: dict) -> str:
        """Generate HMAC SHA256 signature for authenticated requests."""
        timestamp = str(int(time.time() * 1000))
        message = f"{timestamp}{endpoint}{str(params)}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature, timestamp

    def _rate_limit(self):
        """Enforce rate limiting between API calls."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _request(self, method: str, endpoint: str, params: dict = None,
                 data: dict = None, retries: int = 3) -> Optional[Dict]:
        """Make authenticated API request with retry logic."""
        self._rate_limit()
        url = f"{self.base_url}{endpoint}"
        signature, timestamp = self._sign_request(endpoint, params or {})

        headers = {
            "X-Timestamp": timestamp,
            "X-Signature": signature
        }

        for attempt in range(retries):
            try:
                if method == "GET":
                    resp = self.session.get(url, params=params, headers=headers, timeout=10)
                elif method == "POST":
                    resp = self.session.post(url, json=data, headers=headers, timeout=10)
                elif method == "DELETE":
                    resp = self.session.delete(url, params=params, headers=headers, timeout=10)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                resp.raise_for_status()
                return resp.json()

            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error on {endpoint}: {e} (attempt {attempt+1}/{retries})")
                if resp.status_code in [400, 401, 403]:
                    break  # Don't retry auth errors
                time.sleep(2 ** attempt)

            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error on {endpoint}: {e} (attempt {attempt+1}/{retries})")
                time.sleep(2 ** attempt)

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on {endpoint} (attempt {attempt+1}/{retries})")
                time.sleep(1)

        return None

    # ─────────────────────────────────────────────
    # ACCOUNT
    # ─────────────────────────────────────────────

    def get_account_info(self) -> Optional[Dict]:
        """Get account balance, equity, margin info."""
        return self._request("GET", "/account")

    def get_account_balance(self) -> float:
        """Get current account balance as float."""
        info = self.get_account_info()
        if info:
            return float(info.get("balance", 0))
        return 0.0

    def get_equity(self) -> float:
        """Get current equity (balance + unrealized P&L)."""
        info = self.get_account_info()
        if info:
            return float(info.get("equity", 0))
        return 0.0

    # ─────────────────────────────────────────────
    # MARKET DATA
    # ─────────────────────────────────────────────

    def get_price(self, symbol: str) -> Optional[Dict]:
        """Get current bid/ask price for a symbol."""
        return self._request("GET", "/quotes", params={"symbol": symbol})

    def get_prices_bulk(self, symbols: List[str]) -> Optional[Dict]:
        """Get prices for multiple symbols at once."""
        return self._request("GET", "/quotes/bulk",
                             params={"symbols": ",".join(symbols)})

    def get_ohlcv(self, symbol: str, timeframe: str = "1h",
                  limit: int = 500) -> Optional[List[Dict]]:
        """
        Get OHLCV candlestick data.
        Timeframes: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w
        """
        return self._request("GET", "/candles", params={
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit
        })

    def get_ohlcv_range(self, symbol: str, timeframe: str,
                        start: datetime, end: datetime) -> Optional[List[Dict]]:
        """Get OHLCV data for a specific date range."""
        return self._request("GET", "/candles", params={
            "symbol": symbol,
            "timeframe": timeframe,
            "from": int(start.timestamp()),
            "to": int(end.timestamp())
        })

    def get_orderbook(self, symbol: str, depth: int = 20) -> Optional[Dict]:
        """Get current order book depth."""
        return self._request("GET", "/orderbook", params={
            "symbol": symbol,
            "depth": depth
        })

    # ─────────────────────────────────────────────
    # TRADING
    # ─────────────────────────────────────────────

    def place_order(self, symbol: str, side: str, order_type: str,
                    volume: float, price: float = None,
                    stop_loss: float = None, take_profit: float = None,
                    comment: str = "APEX") -> Optional[Dict]:
        """
        Place a trade order.
        Args:
            symbol: e.g. "USOIL"
            side: "buy" or "sell"
            order_type: "market" or "limit"
            volume: lot size
            price: required for limit orders
            stop_loss: SL price
            take_profit: TP price
            comment: order label
        """
        if self.mode == "paper":
            return self._simulate_order(symbol, side, order_type, volume,
                                        price, stop_loss, take_profit)

        data = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "volume": volume,
            "comment": comment
        }
        if price:
            data["price"] = price
        if stop_loss:
            data["stopLoss"] = stop_loss
        if take_profit:
            data["takeProfit"] = take_profit

        result = self._request("POST", "/orders", data=data)
        if result:
            logger.info(f"Order placed: {side.upper()} {volume} {symbol} | "
                        f"SL={stop_loss} TP={take_profit}")
        return result

    def close_position(self, position_id: str, volume: float = None) -> Optional[Dict]:
        """Close an open position (fully or partially)."""
        if self.mode == "paper":
            return {"status": "closed", "id": position_id}

        data = {"id": position_id}
        if volume:
            data["volume"] = volume
        return self._request("POST", f"/positions/{position_id}/close", data=data)

    def modify_order(self, order_id: str, stop_loss: float = None,
                     take_profit: float = None) -> Optional[Dict]:
        """Modify SL/TP of an existing order."""
        if self.mode == "paper":
            return {"status": "modified", "id": order_id}

        data = {}
        if stop_loss:
            data["stopLoss"] = stop_loss
        if take_profit:
            data["takeProfit"] = take_profit
        return self._request("POST", f"/orders/{order_id}/modify", data=data)

    def cancel_order(self, order_id: str) -> Optional[Dict]:
        """Cancel a pending order."""
        if self.mode == "paper":
            return {"status": "cancelled", "id": order_id}
        return self._request("DELETE", f"/orders/{order_id}")

    # ─────────────────────────────────────────────
    # POSITIONS & HISTORY
    # ─────────────────────────────────────────────

    def get_open_positions(self) -> List[Dict]:
        """Get all currently open positions."""
        result = self._request("GET", "/positions")
        return result if result else []

    def get_pending_orders(self) -> List[Dict]:
        """Get all pending orders."""
        result = self._request("GET", "/orders/pending")
        return result if result else []

    def get_trade_history(self, from_date: datetime = None,
                          to_date: datetime = None) -> List[Dict]:
        """Get closed trade history."""
        params = {}
        if from_date:
            params["from"] = int(from_date.timestamp())
        if to_date:
            params["to"] = int(to_date.timestamp())
        result = self._request("GET", "/history/trades", params=params)
        return result if result else []

    def get_daily_pnl(self) -> float:
        """Calculate today's realized P&L."""
        today = datetime.now().replace(hour=0, minute=0, second=0)
        trades = self.get_trade_history(from_date=today)
        return sum(float(t.get("profit", 0)) for t in trades)

    # ─────────────────────────────────────────────
    # PAPER TRADING SIMULATION
    # ─────────────────────────────────────────────

    def _simulate_order(self, symbol: str, side: str, order_type: str,
                         volume: float, price: float, stop_loss: float,
                         take_profit: float) -> Dict:
        """Simulate order execution for paper trading."""
        import uuid
        order_id = str(uuid.uuid4())[:8]
        logger.info(f"[PAPER] {side.upper()} {volume} {symbol} | "
                    f"SL={stop_loss} TP={take_profit}")
        return {
            "id": order_id,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "type": order_type,
            "price": price,
            "stopLoss": stop_loss,
            "takeProfit": take_profit,
            "status": "filled",
            "timestamp": datetime.now().isoformat(),
            "paper": True
        }
