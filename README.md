import numpy as np
import time
import math
import random
from datetime import datetime, timedelta
from typing import Optional
import os

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

OANDA_BASE_URL = "https://api-fxpractice.oanda.com"

INSTRUMENT_MAP = {
    "WTI":    "BCO_USD",
    "BRENT":  "BCO_USD",
    "NATGAS": "NATGAS_USD",
    "GOLD":   "XAU_USD",
    "SILVER": "XAG_USD",
}

BASE_PRICES = {
    "WTI": 78.50, "BRENT": 82.30, "NATGAS": 1.95,
    "GOLD": 2180.0, "SILVER": 24.50,
}

VOLATILITY = {
    "WTI": 0.018, "BRENT": 0.016, "NATGAS": 0.035,
    "GOLD": 0.008, "SILVER": 0.020,
}


class PriceSimulator:
    def __init__(self):
        self.prices = {k: v for k, v in BASE_PRICES.items()}

    def _gbm_step(self, price, vol, dt=1/252):
        return price * math.exp(np.random.normal(0, vol * math.sqrt(dt)))

    def get_candles(self, instrument, count=100):
        base = BASE_PRICES[instrument]
        vol = VOLATILITY[instrument]
        prices = [base]
        for _ in range(count - 1):
            prices.append(self._gbm_step(prices[-1], vol * 15))
        candles = []
        now = datetime.utcnow()
        for i, close in enumerate(prices):
            ts = now - timedelta(minutes=15 * (count - i))
            open_ = prices[i - 1] if i > 0 else close
            high = close + abs(np.random.normal(0, close * vol * 0.3))
            low = close - abs(np.random.normal(0, close * vol * 0.3))
            candles.append({
                "time": ts.isoformat(),
                "mid": {
                    "o": str(round(open_, 5)),
                    "h": str(round(max(open_, close, high), 5)),
                    "l": str(round(min(open_, close, low), 5)),
                    "c": str(round(close, 5)),
                }
            })
        return {"candles": candles, "instrument": instrument, "granularity": "M15"}

    def get_price(self, instrument):
        price = self.prices[instrument]
        self.prices[instrument] = self._gbm_step(price, VOLATILITY[instrument], 1/96)
        spread = price * 0.0003
        bid = self.prices[instrument] - spread / 2
        ask = self.prices[instrument] + spread / 2
        return {
            "instrument": instrument,
            "bid": round(bid, 5),
            "ask": round(ask, 5),
            "mid": round((bid + ask) / 2, 5),
            "time": datetime.utcnow().isoformat(),
            "status": "tradeable"
        }

    def get_account(self):
        return {
            "id": "DEMO-001",
            "balance": "100000.00",
            "currency": "USD",
            "unrealizedPL": "0.00",
            "nav": "100000.00",
            "marginUsed": "0.00",
            "marginAvailable": "100000.00",
            "openTradeCount": 0,
            "alias": "APEX Demo Account",
        }


class OANDAConnector:
    def __init__(self, api_key=None, account_id=None):
        self.api_key = api_key or os.environ.get("OANDA_API_KEY", "")
        self.account_id = account_id or os.environ.get("OANDA_ACCOUNT_ID", "")
        self.simulator = PriceSimulator()
        self.live = False
        self.headers = {}

        if self.api_key and HAS_REQUESTS:
            self.live = True
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept-Datetime-Format": "RFC3339",
            }
        else:
            print("[APEX] No API key — simulation mode")

    def _get(self, endpoint):
        if not self.live:
            return {}
        url = f"{OANDA_BASE_URL}{endpoint}"
        resp = requests.get(url, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint, data):
        if not self.live:
            return {}
        url = f"{OANDA_BASE_URL}{endpoint}"
        resp = requests.post(url, headers=self.headers, json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_account(self):
        if not self.live:
            return self.simulator.get_account()
        data = self._get(f"/v3/accounts/{self.account_id}/summary")
        return data.get("account", {})

    def get_candles(self, instrument, count=100, granularity="M15"):
        if not self.live:
            return self.simulator.get_candles(instrument, count)
        oanda_inst = INSTRUMENT_MAP.get(instrument, instrument)
        return self._get(
            f"/v3/instruments/{oanda_inst}/candles"
            f"?count={count}&granularity={granularity}&price=M"
        )

    def get_price(self, instrument):
        if not self.live:
            return self.simulator.get_price(instrument)
        oanda_inst = INSTRUMENT_MAP.get(instrument, instrument)
        data = self._get(f"/v3/accounts/{self.account_id}/pricing?instruments={oanda_inst}")
        prices = data.get("prices", [{}])[0]
        bid = float(prices.get("bids", [{"price": 0}])[0]["price"])
        ask = float(prices.get("asks", [{"price": 0}])[0]["price"])
        return {"instrument": instrument, "bid": bid, "ask": ask,
                "mid": (bid + ask) / 2, "time": datetime.utcnow().isoformat(),
                "status": "tradeable"}

    def place_order(self, instrument, units, direction, stop_loss, take_profit):
        signed_units = units if direction == "BUY" else -units
        oanda_inst = INSTRUMENT_MAP.get(instrument, instrument)
        order_body = {
            "order": {
                "type": "MARKET",
                "instrument": oanda_inst,
                "units": str(signed_units),
                "stopLossOnFill": {"price": str(round(stop_loss, 5))},
                "takeProfitOnFill": {"price": str(round(take_profit, 5))},
                "timeInForce": "FOK",
            }
        }
        if not self.live:
            price = self.simulator.get_price(instrument)
            return {"orderFillTransaction": {
                "id": f"SIM-{int(time.time())}",
                "instrument": oanda_inst,
                "units": str(signed_units),
                "price": str(price["mid"]),
                "time": datetime.utcnow().isoformat(),
                "pl": "0.00",
            }}
        return self._post(f"/v3/accounts/{self.account_id}/orders", order_body)

    def get_open_trades(self):
        if not self.live:
            return []
        data = self._get(f"/v3/accounts/{self.account_id}/openTrades")
        return data.get("trades", [])

    def close_trade(self, trade_id):
        if not self.live:
            return {"orderFillTransaction": {"pl": str(round(random.gauss(50, 200), 2))}}
        return self._post(f"/v3/accounts/{self.account_id}/trades/{trade_id}/close", {})










mmm









def __init__(self, api_key=None, account_id=None):
    self.api_key     = api_key or os.environ.get("OANDA_API_KEY", "")
    self.account_id  = account_id or os.environ.get("OANDA_ACCOUNT_ID", "")
    self.simulator   = PriceSimulator()
    self.headers     = {}  # always initialise headers

    if self.api_key and HAS_REQUESTS:
        self.live = True
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept-Datetime-Format": "RFC3339",
        }
    else:
        self.live = False
        print("[APEX] No API key found — running in simulation mode")





def get_city_name(cert_owner):

    if not isinstance(cert_owner, str) or not cert_owner.strip():
        return None

    exempt_words = ["ltd.", "ltd", "s.i.u",
                    "s.a.", "s.a", "s.r.o.",
                    "s.r.o", "s.i.", "s.i",
                    "s.p.a", "s.p.a.", "s.l.u",
                    "s.l.u", "a.s", "a.s.",
                    "s.l", "s.l.", "inc.", "inc",
                    ". ltd", "-", "oils", "l.p.",
                    "llc", "l.l.c.", "llc.", "lp", "inc.."]

    all_parts = [p.strip() for p in cert_owner.split(",") if p.strip()]

    # Extract country correctly — always the LAST part
    country = all_parts[-1].strip().lower() if all_parts else ""

    # Middle parts only (drop company and country)
    parts = [p.lower() for p in all_parts[1:-1]]

    tokens = [
        tok
        for tok in parts
        if tok
        and tok not in exempt_words
        and not any(w in CITY_STOPWORDS for w in tok.split())
        and not every_word_has_digit(tok)
        and not (len(tok) == 2 and tok.isupper())  # drop US state codes like TX, IL, CA
    ]

    if len(tokens) == 1:
        return " ".join([w for w in tokens[0].split() if not w.isnumeric()]).title()
    elif len(tokens) >= 2:
        if country in ("united states", "china"):
            return " ".join([w for w in tokens[-2].split() if not w.isnumeric()]).title()
        else:
            return " ".join([w for w in tokens[-1].split() if not w.isnumeric()]).title()

    return None
