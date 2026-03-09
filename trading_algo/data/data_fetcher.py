"""
APEX TRADING SYSTEM - Data Fetcher
====================================
Fetches and caches market data, fundamental data (EIA oil inventories,
COT reports, economic calendar) and news sentiment for ML features.
"""

import os
import json
import time
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from config.config import (
    ALPHA_VANTAGE_KEY, EIA_API_KEY, NEWS_API_KEY,
    ALL_MARKETS, DATA_DIR, LOOKBACK_PERIOD_DAYS
)

logger = logging.getLogger(__name__)
Path(DATA_DIR).mkdir(exist_ok=True)


class DataFetcher:
    """
    Fetches OHLCV, fundamentals, and news data.
    Caches locally to avoid redundant API calls.
    """

    CACHE_EXPIRY = {
        "ohlcv_1h": 3600,
        "ohlcv_1d": 86400,
        "fundamentals": 3600 * 4,
        "news": 1800,
        "eia": 86400
    }

    def __init__(self, vantage_api=None):
        self.vantage = vantage_api
        self.cache = {}
        self.cache_timestamps = {}

    # ─────────────────────────────────────────────
    # OHLCV DATA
    # ─────────────────────────────────────────────

    def get_ohlcv_df(self, symbol: str, timeframe: str = "1h",
                     periods: int = 500) -> pd.DataFrame:
        """
        Get OHLCV as a clean pandas DataFrame with datetime index.
        Falls back to synthetic data if API not connected.
        """
        cache_key = f"ohlcv_{symbol}_{timeframe}"
        if self._is_cached(cache_key):
            return self.cache[cache_key]

        df = None

        # Try Vantage API first
        if self.vantage:
            raw = self.vantage.get_ohlcv(symbol, timeframe, periods)
            if raw:
                df = self._parse_ohlcv(raw)

        # Fallback: Alpha Vantage for commodities
        if df is None and ALPHA_VANTAGE_KEY != "YOUR_ALPHA_VANTAGE_KEY":
            df = self._fetch_alpha_vantage(symbol, timeframe)

        # Fallback: Generate realistic synthetic data for testing
        if df is None:
            logger.warning(f"Using synthetic data for {symbol} — configure API keys")
            df = self._generate_synthetic_ohlcv(symbol, periods)

        if df is not None:
            df = self._add_technical_indicators(df)
            self._set_cache(cache_key, df)

        return df

    def _parse_ohlcv(self, raw: List[Dict]) -> pd.DataFrame:
        """Parse raw API candle data into DataFrame."""
        df = pd.DataFrame(raw)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        df.set_index('timestamp', inplace=True)
        df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        df.sort_index(inplace=True)
        return df

    def _fetch_alpha_vantage(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Fetch from Alpha Vantage as backup data source."""
        av_symbols = {
            "USOIL": "WTI", "UKOIL": "BRENT",
            "XAUUSD": "GOLD", "XAGUSD": "SILVER",
            "NGAS": "NATURAL_GAS"
        }
        av_sym = av_symbols.get(symbol, symbol)

        try:
            url = (f"https://www.alphavantage.co/query"
                   f"?function=TIME_SERIES_DAILY&symbol={av_sym}"
                   f"&outputsize=full&apikey={ALPHA_VANTAGE_KEY}")
            resp = requests.get(url, timeout=10).json()

            ts = resp.get("Time Series (Daily)", {})
            if not ts:
                return None

            records = []
            for date_str, vals in ts.items():
                records.append({
                    "timestamp": pd.to_datetime(date_str),
                    "open": float(vals["1. open"]),
                    "high": float(vals["2. high"]),
                    "low": float(vals["3. low"]),
                    "close": float(vals["4. close"]),
                    "volume": float(vals.get("5. volume", 0))
                })
            df = pd.DataFrame(records)
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)
            return df

        except Exception as e:
            logger.error(f"Alpha Vantage error for {symbol}: {e}")
            return None

    def _generate_synthetic_ohlcv(self, symbol: str, periods: int) -> pd.DataFrame:
        """Generate realistic synthetic price data for testing."""
        np.random.seed(hash(symbol) % 2**32)

        base_prices = {
            "XAUUSD": 2000.0, "XAGUSD": 24.0,
            "USOIL": 78.0,  "UKOIL": 82.0,
            "NGAS": 2.5,    "HEAT": 2.8,
            "RBOB": 2.4,    "CARBON": 65.0
        }
        base = base_prices.get(symbol, 100.0)
        volatility = base * 0.015

        # Geometric Brownian Motion
        returns = np.random.normal(0.0002, volatility / base, periods)
        closes = base * np.exp(np.cumsum(returns))

        df = pd.DataFrame(index=pd.date_range(
            end=datetime.now(), periods=periods, freq="1h"
        ))
        df["close"] = closes
        noise = np.random.uniform(0.001, 0.005, periods)
        df["high"] = df["close"] * (1 + noise)
        df["low"] = df["close"] * (1 - noise)
        df["open"] = df["close"].shift(1).fillna(base)
        df["volume"] = np.random.randint(1000, 50000, periods).astype(float)
        return df[["open", "high", "low", "close", "volume"]]

    # ─────────────────────────────────────────────
    # TECHNICAL INDICATORS
    # ─────────────────────────────────────────────

    def _add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add comprehensive technical indicators for ML features."""
        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]

        # Moving Averages
        for p in [9, 20, 50, 100, 200]:
            df[f"sma_{p}"] = c.rolling(p).mean()
            df[f"ema_{p}"] = c.ewm(span=p, adjust=False).mean()

        # RSI
        df["rsi_14"] = self._rsi(c, 14)
        df["rsi_21"] = self._rsi(c, 21)

        # MACD
        ema12 = c.ewm(span=12).mean()
        ema26 = c.ewm(span=26).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # Bollinger Bands
        sma20 = c.rolling(20).mean()
        std20 = c.rolling(20).std()
        df["bb_upper"] = sma20 + 2 * std20
        df["bb_lower"] = sma20 - 2 * std20
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / sma20
        df["bb_pos"] = (c - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

        # ATR
        tr = pd.concat([
            h - l,
            (h - c.shift()).abs(),
            (l - c.shift()).abs()
        ], axis=1).max(axis=1)
        df["atr_14"] = tr.rolling(14).mean()
        df["atr_pct"] = df["atr_14"] / c

        # Stochastic
        low14 = l.rolling(14).min()
        high14 = h.rolling(14).max()
        df["stoch_k"] = 100 * (c - low14) / (high14 - low14)
        df["stoch_d"] = df["stoch_k"].rolling(3).mean()

        # ADX (Average Directional Index)
        df["adx"] = self._adx(h, l, c, 14)

        # Williams %R
        df["williams_r"] = -100 * (high14 - c) / (high14 - low14)

        # OBV (On Balance Volume)
        obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
        df["obv"] = obv
        df["obv_sma"] = obv.rolling(20).mean()

        # Price momentum
        for p in [1, 5, 10, 20]:
            df[f"momentum_{p}"] = c.pct_change(p)

        # Volatility
        df["volatility_20"] = c.pct_change().rolling(20).std()
        df["volatility_50"] = c.pct_change().rolling(50).std()

        # Volume features
        df["volume_sma_20"] = v.rolling(20).mean()
        df["volume_ratio"] = v / df["volume_sma_20"]

        # Candle features
        df["body_size"] = (df["close"] - df["open"]).abs() / df["open"]
        df["upper_wick"] = (h - df[["close", "open"]].max(axis=1)) / df["open"]
        df["lower_wick"] = (df[["close", "open"]].min(axis=1) - l) / df["open"]
        df["is_bullish"] = (df["close"] > df["open"]).astype(int)

        return df

    def _rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def _adx(self, high, low, close, period=14) -> pd.Series:
        tr = pd.concat([high - low,
                        (high - close.shift()).abs(),
                        (low - close.shift()).abs()], axis=1).max(axis=1)
        dm_plus = ((high - high.shift()) > (low.shift() - low))
        dm_minus = ((low.shift() - low) > (high - high.shift()))
        dmp = (high - high.shift()).clip(lower=0).where(dm_plus, 0)
        dmm = (low.shift() - low).clip(lower=0).where(dm_minus, 0)
        tr_smooth = tr.rolling(period).mean()
        dmp_smooth = dmp.rolling(period).mean()
        dmm_smooth = dmm.rolling(period).mean()
        di_plus = 100 * dmp_smooth / tr_smooth
        di_minus = 100 * dmm_smooth / tr_smooth
        dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus)
        return dx.rolling(period).mean()

    # ─────────────────────────────────────────────
    # FUNDAMENTAL DATA
    # ─────────────────────────────────────────────

    def get_eia_oil_inventories(self) -> Dict:
        """
        Fetch EIA weekly crude oil inventory data.
        Inventory draws are bullish for oil prices.
        """
        cache_key = "eia_inventories"
        if self._is_cached(cache_key, ttl=self.CACHE_EXPIRY["eia"]):
            return self.cache[cache_key]

        result = {"crude_inventory_change": 0, "gasoline_change": 0,
                  "distillate_change": 0, "cushing_change": 0}

        if EIA_API_KEY == "YOUR_EIA_API_KEY":
            return result

        try:
            # EIA crude oil stocks series
            series_ids = {
                "crude_inventory_change": "PET.WCRSTUS1.W",
                "gasoline_change": "PET.WGTSTUS1.W",
                "distillate_change": "PET.WDISTUS1.W",
                "cushing_change": "PET.WCSSTUS1.W"
            }
            for key, series_id in series_ids.items():
                url = (f"https://api.eia.gov/v2/seriesid/{series_id}"
                       f"?api_key={EIA_API_KEY}&length=4")
                resp = requests.get(url, timeout=10).json()
                data = resp.get("response", {}).get("data", [])
                if len(data) >= 2:
                    result[key] = float(data[0]["value"]) - float(data[1]["value"])

            self._set_cache(cache_key, result)

        except Exception as e:
            logger.error(f"EIA data fetch error: {e}")

        return result

    def get_news_sentiment(self, symbols: List[str]) -> Dict[str, float]:
        """
        Fetch recent news and compute sentiment scores per commodity.
        Returns dict of {symbol: sentiment_score} where -1=bearish, +1=bullish.
        """
        cache_key = "news_sentiment"
        if self._is_cached(cache_key, ttl=self.CACHE_EXPIRY["news"]):
            return self.cache[cache_key]

        sentiments = {s: 0.0 for s in symbols}

        if NEWS_API_KEY == "YOUR_NEWS_API_KEY":
            return sentiments

        try:
            from textblob import TextBlob

            queries = {
                "USOIL": "crude oil WTI price",
                "UKOIL": "brent crude oil",
                "XAUUSD": "gold price",
                "XAGUSD": "silver price",
                "NGAS": "natural gas price"
            }

            for symbol in symbols:
                query = queries.get(symbol, symbol)
                url = (f"https://newsapi.org/v2/everything"
                       f"?q={query}&sortBy=publishedAt&pageSize=10"
                       f"&apiKey={NEWS_API_KEY}")
                resp = requests.get(url, timeout=10).json()
                articles = resp.get("articles", [])

                if articles:
                    scores = []
                    for article in articles[:10]:
                        text = (article.get("title", "") + " " +
                                article.get("description", ""))
                        if text.strip():
                            blob = TextBlob(text)
                            scores.append(blob.sentiment.polarity)
                    sentiments[symbol] = np.mean(scores) if scores else 0.0

            self._set_cache(cache_key, sentiments)

        except ImportError:
            logger.warning("textblob not installed — news sentiment disabled")
        except Exception as e:
            logger.error(f"News sentiment error: {e}")

        return sentiments

    def get_economic_calendar_features(self) -> Dict:
        """
        Return upcoming high-impact economic events as binary features.
        Key events: Fed meetings, OPEC meetings, NFP, CPI, EIA reports.
        """
        now = datetime.now()
        features = {
            "days_to_fomc": 999,
            "days_to_opec": 999,
            "days_to_nfp": 999,
            "days_to_eia_report": 999,
            "is_high_impact_week": 0
        }

        # EIA Petroleum Status Report is every Wednesday
        days_to_wednesday = (2 - now.weekday()) % 7
        features["days_to_eia_report"] = days_to_wednesday if days_to_wednesday > 0 else 7

        # NFP is first Friday of the month
        first_friday = self._get_next_first_friday()
        features["days_to_nfp"] = (first_friday - now).days

        if features["days_to_nfp"] <= 3 or features["days_to_eia_report"] <= 1:
            features["is_high_impact_week"] = 1

        return features

    def _get_next_first_friday(self) -> datetime:
        """Calculate next NFP release date (first Friday of month)."""
        now = datetime.now()
        for month_offset in range(2):
            year = now.year + (now.month + month_offset - 1) // 12
            month = (now.month + month_offset - 1) % 12 + 1
            first_day = datetime(year, month, 1)
            first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
            if first_friday > now:
                return first_friday
        return datetime.now() + timedelta(days=30)

    # ─────────────────────────────────────────────
    # CACHE MANAGEMENT
    # ─────────────────────────────────────────────

    def _is_cached(self, key: str, ttl: int = 3600) -> bool:
        if key not in self.cache:
            return False
        age = time.time() - self.cache_timestamps.get(key, 0)
        return age < ttl

    def _set_cache(self, key: str, value):
        self.cache[key] = value
        self.cache_timestamps[key] = time.time()

    def clear_cache(self):
        self.cache.clear()
        self.cache_timestamps.clear()
        logger.info("Data cache cleared")
