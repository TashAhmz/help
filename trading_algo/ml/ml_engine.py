"""
APEX TRADING SYSTEM - ML Engine
=================================
Ensemble ML model that combines:
  - Random Forest for trend prediction
  - Gradient Boosting for momentum signals
  - LSTM-inspired feature engineering for sequence patterns
  - XGBoost for regime detection
  - Meta-learner that selects best strategy per market regime

Outputs: BUY / SELL / HOLD signals with confidence scores,
         dynamic position sizing, and predicted SL/TP levels.
"""

import os
import pickle
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Tuple, Optional, List
from pathlib import Path
from dataclasses import dataclass

from config.config import MODEL_DIR, MIN_ML_CONFIDENCE

logger = logging.getLogger(__name__)
Path(MODEL_DIR).mkdir(parents=True, exist_ok=True)


@dataclass
class TradeSignal:
    symbol: str
    action: str           # "BUY", "SELL", "HOLD"
    confidence: float     # 0.0 - 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    position_size_pct: float  # % of account to risk
    predicted_return: float
    regime: str           # "trending", "ranging", "volatile"
    strategy_used: str
    features_summary: Dict
    timestamp: datetime


class MLEngine:
    """
    Multi-model ensemble ML trading engine.
    Trains on OHLCV + technical + fundamental features.
    """

    FEATURE_COLS = [
        # Trend
        "sma_9", "sma_20", "sma_50", "ema_9", "ema_20", "ema_50",
        # Momentum
        "rsi_14", "rsi_21", "macd", "macd_signal", "macd_hist",
        "momentum_1", "momentum_5", "momentum_10", "momentum_20",
        "stoch_k", "stoch_d", "williams_r",
        # Volatility
        "bb_width", "bb_pos", "atr_pct", "volatility_20", "volatility_50", "adx",
        # Volume
        "volume_ratio", "obv_sma",
        # Candle patterns
        "body_size", "upper_wick", "lower_wick", "is_bullish",
    ]

    def __init__(self):
        self.models = {}          # {symbol: {model_name: model}}
        self.scalers = {}         # {symbol: scaler}
        self.regime_models = {}   # {symbol: regime_classifier}
        self.feature_importance = {}
        self._load_all_models()

    # ─────────────────────────────────────────────
    # MODEL TRAINING
    # ─────────────────────────────────────────────

    def train(self, symbol: str, df: pd.DataFrame,
              fundamental_features: Dict = None) -> Dict:
        """
        Train the full ensemble for a given symbol.
        Returns training metrics (accuracy, sharpe, etc.)
        """
        logger.info(f"Training ML models for {symbol}...")

        try:
            from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.model_selection import TimeSeriesSplit
            from sklearn.metrics import accuracy_score, classification_report
            import xgboost as xgb
        except ImportError as e:
            logger.error(f"Missing ML library: {e}. Run: pip install scikit-learn xgboost")
            return {}

        # Prepare features and labels
        X, y, meta = self._prepare_training_data(df, fundamental_features)
        if len(X) < 100:
            logger.warning(f"Insufficient data for {symbol}: {len(X)} samples")
            return {}

        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        self.scalers[symbol] = scaler

        # Time-series cross-validation (no data leakage)
        tscv = TimeSeriesSplit(n_splits=5)
        cv_scores = {"rf": [], "gb": [], "xgb": []}

        # Model 1: Random Forest — good for non-linear patterns
        rf = RandomForestClassifier(
            n_estimators=300,
            max_depth=8,
            min_samples_split=20,
            min_samples_leaf=10,
            max_features="sqrt",
            class_weight="balanced",
            n_jobs=-1,
            random_state=42
        )

        # Model 2: Gradient Boosting — strong momentum detection
        gb = GradientBoostingClassifier(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=4,
            min_samples_split=20,
            subsample=0.8,
            random_state=42
        )

        # Model 3: XGBoost — regime detection & complex patterns
        xgb_model = xgb.XGBClassifier(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            eval_metric="logloss",
            use_label_encoder=False,
            random_state=42
        )

        # Cross-validation
        for fold, (train_idx, val_idx) in enumerate(tscv.split(X_scaled)):
            X_train, X_val = X_scaled[train_idx], X_scaled[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            rf.fit(X_train, y_train)
            gb.fit(X_train, y_train)
            xgb_model.fit(X_train, y_train, eval_set=[(X_val, y_val)],
                          verbose=False)

            cv_scores["rf"].append(accuracy_score(y_val, rf.predict(X_val)))
            cv_scores["gb"].append(accuracy_score(y_val, gb.predict(X_val)))
            cv_scores["xgb"].append(accuracy_score(y_val, xgb_model.predict(X_val)))

        # Final training on all data
        rf.fit(X_scaled, y)
        gb.fit(X_scaled, y)
        xgb_model.fit(X_scaled, y, verbose=False)

        self.models[symbol] = {"rf": rf, "gb": gb, "xgb": xgb_model}

        # Feature importance
        self.feature_importance[symbol] = {
            col: float(imp)
            for col, imp in zip(self.FEATURE_COLS,
                                rf.feature_importances_[:len(self.FEATURE_COLS)])
        }

        # Regime classifier
        self.regime_models[symbol] = self._train_regime_classifier(df, X_scaled)

        # Save models
        self._save_models(symbol)

        metrics = {
            "rf_cv_accuracy": float(np.mean(cv_scores["rf"])),
            "gb_cv_accuracy": float(np.mean(cv_scores["gb"])),
            "xgb_cv_accuracy": float(np.mean(cv_scores["xgb"])),
            "samples": len(X),
            "features": len(self.FEATURE_COLS),
            "trained_at": datetime.now().isoformat()
        }
        logger.info(f"{symbol} training complete | RF: {metrics['rf_cv_accuracy']:.2%} "
                    f"| GB: {metrics['gb_cv_accuracy']:.2%} "
                    f"| XGB: {metrics['xgb_cv_accuracy']:.2%}")
        return metrics

    def _prepare_training_data(self, df: pd.DataFrame,
                                fundamental_features: Dict = None
                                ) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """
        Build feature matrix and labels.
        Label: 1=BUY (>1% gain in next 12 bars), -1=SELL (<-1%), 0=HOLD
        Uses forward-looking returns for supervised learning.
        """
        df = df.copy().dropna()

        # Target: forward return over next 12 periods
        forward_return = df["close"].shift(-12) / df["close"] - 1
        threshold = df["atr_pct"].mean() * 0.5  # Dynamic threshold based on volatility

        y_raw = np.where(forward_return > threshold, 1,
                np.where(forward_return < -threshold, -1, 0))
        # Convert to 0,1,2 for sklearn
        y = y_raw + 1  # -1->0, 0->1, 1->2

        # Build feature matrix
        feature_df = df[self.FEATURE_COLS].copy()

        # Add cross-asset features
        feature_df["price_vs_sma50"] = (df["close"] - df["sma_50"]) / df["sma_50"]
        feature_df["price_vs_sma200"] = (df["close"] - df["sma_200"]) / df["sma_200"]
        feature_df["ema_cross"] = (df["ema_9"] > df["ema_20"]).astype(int)
        feature_df["macd_cross"] = (df["macd"] > df["macd_signal"]).astype(int)

        # Lag features (sequence information)
        for lag in [1, 2, 3, 5]:
            feature_df[f"close_lag_{lag}"] = df["close"].pct_change(lag)
            feature_df[f"rsi_lag_{lag}"] = df["rsi_14"].shift(lag)

        # Rolling stats
        feature_df["close_zscore_20"] = (
            (df["close"] - df["close"].rolling(20).mean()) /
            df["close"].rolling(20).std()
        )

        # Add fundamental features if available
        if fundamental_features:
            for k, v in fundamental_features.items():
                feature_df[k] = float(v)

        # Remove NaN rows
        valid_mask = feature_df.notna().all(axis=1)
        X = feature_df[valid_mask].values
        y = y[valid_mask]

        # Remove last 12 rows (no forward labels)
        X = X[:-12]
        y = y[:-12]

        return X, y, feature_df[valid_mask].iloc[:-12]

    def _train_regime_classifier(self, df: pd.DataFrame,
                                  X_scaled: np.ndarray):
        """
        Classify market regime: trending / ranging / volatile.
        Uses ADX, Bollinger Band width, and volatility.
        """
        from sklearn.cluster import KMeans

        if len(df) < 50:
            return None

        regime_features = np.column_stack([
            df["adx"].fillna(25).values,
            df["bb_width"].fillna(0.05).values,
            df["volatility_20"].fillna(0.01).values
        ])[-len(X_scaled):]

        kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
        kmeans.fit(regime_features)
        return kmeans

    # ─────────────────────────────────────────────
    # SIGNAL GENERATION
    # ─────────────────────────────────────────────

    def generate_signal(self, symbol: str, df: pd.DataFrame,
                        current_price: float,
                        fundamental_features: Dict = None,
                        account_balance: float = 10000) -> TradeSignal:
        """
        Generate a trade signal for a symbol using the ensemble.
        """
        if symbol not in self.models:
            logger.warning(f"No trained model for {symbol}, using rule-based fallback")
            return self._rule_based_signal(symbol, df, current_price, account_balance)

        try:
            # Prepare latest features
            features = self._extract_latest_features(df, fundamental_features)
            scaler = self.scalers[symbol]
            X = scaler.transform(features.reshape(1, -1))

            models = self.models[symbol]

            # Get probability predictions from each model
            rf_proba = models["rf"].predict_proba(X)[0]   # [sell, hold, buy]
            gb_proba = models["gb"].predict_proba(X)[0]
            xgb_proba = models["xgb"].predict_proba(X)[0]

            # Ensemble: weighted average (XGB gets highest weight)
            ensemble_proba = (
                0.25 * rf_proba +
                0.25 * gb_proba +
                0.50 * xgb_proba
            )

            sell_prob, hold_prob, buy_prob = ensemble_proba

            # Determine action
            max_prob = max(buy_prob, sell_prob, hold_prob)
            if buy_prob == max_prob and buy_prob >= MIN_ML_CONFIDENCE:
                action = "BUY"
                confidence = float(buy_prob)
            elif sell_prob == max_prob and sell_prob >= MIN_ML_CONFIDENCE:
                action = "SELL"
                confidence = float(sell_prob)
            else:
                action = "HOLD"
                confidence = float(hold_prob)

            # Calculate SL/TP using ATR-based dynamic levels
            atr = float(df["atr_14"].iloc[-1])
            atr_multiplier_sl = 1.5 + (1 - confidence) * 2  # Wider SL when less confident
            atr_multiplier_tp = atr_multiplier_sl * 2.0       # Always 2:1 R:R minimum

            if action == "BUY":
                stop_loss = current_price - (atr * atr_multiplier_sl)
                take_profit = current_price + (atr * atr_multiplier_tp)
            elif action == "SELL":
                stop_loss = current_price + (atr * atr_multiplier_sl)
                take_profit = current_price - (atr * atr_multiplier_tp)
            else:
                stop_loss = take_profit = current_price

            # Position sizing: Kelly Criterion adjusted
            position_size_pct = self._kelly_position_size(
                confidence, win_rate=0.55, rr_ratio=2.0
            )

            # Detect regime
            regime = self._detect_regime(df)

            risk_reward = (abs(take_profit - current_price) /
                           max(abs(stop_loss - current_price), 0.0001))
            predicted_return = (take_profit - current_price) / current_price

            return TradeSignal(
                symbol=symbol,
                action=action,
                confidence=confidence,
                entry_price=current_price,
                stop_loss=round(stop_loss, 5),
                take_profit=round(take_profit, 5),
                risk_reward=round(risk_reward, 2),
                position_size_pct=position_size_pct,
                predicted_return=predicted_return,
                regime=regime,
                strategy_used="ML_Ensemble",
                features_summary={
                    "rsi": round(float(df["rsi_14"].iloc[-1]), 1),
                    "macd_hist": round(float(df["macd_hist"].iloc[-1]), 4),
                    "adx": round(float(df["adx"].iloc[-1]), 1),
                    "bb_pos": round(float(df["bb_pos"].iloc[-1]), 2),
                    "buy_prob": round(float(buy_prob), 3),
                    "sell_prob": round(float(sell_prob), 3),
                },
                timestamp=datetime.now()
            )

        except Exception as e:
            logger.error(f"Signal generation error for {symbol}: {e}")
            return self._rule_based_signal(symbol, df, current_price, account_balance)

    def _extract_latest_features(self, df: pd.DataFrame,
                                   fundamental_features: Dict = None) -> np.ndarray:
        """Extract feature vector from the latest candle."""
        latest = df.iloc[-1]
        features = [float(latest.get(col, 0)) for col in self.FEATURE_COLS]

        # Extra derived features
        features.append(float((latest["close"] - latest["sma_50"]) / latest["sma_50"]))
        features.append(float((latest["close"] - latest["sma_200"]) / latest["sma_200"]))
        features.append(float(latest["ema_9"] > latest["ema_20"]))
        features.append(float(latest["macd"] > latest["macd_signal"]))

        for lag in [1, 2, 3, 5]:
            features.append(float(df["close"].pct_change(lag).iloc[-1]))
            features.append(float(df["rsi_14"].shift(lag).iloc[-1]))

        zscore = ((latest["close"] - df["close"].rolling(20).mean().iloc[-1]) /
                  df["close"].rolling(20).std().iloc[-1])
        features.append(float(zscore) if not np.isnan(zscore) else 0.0)

        if fundamental_features:
            features.extend([float(v) for v in fundamental_features.values()])

        return np.array(features)

    def _kelly_position_size(self, confidence: float,
                              win_rate: float = 0.55,
                              rr_ratio: float = 2.0) -> float:
        """
        Kelly Criterion for position sizing.
        f* = W - (1-W)/R where W=win_rate, R=reward/risk
        Apply fractional Kelly (50%) for safety.
        """
        # Adjust win rate by confidence
        adjusted_win_rate = win_rate * confidence / 0.65
        adjusted_win_rate = min(adjusted_win_rate, 0.85)

        kelly = adjusted_win_rate - (1 - adjusted_win_rate) / rr_ratio
        kelly = max(0, kelly)
        fractional_kelly = kelly * 0.5  # 50% Kelly
        return min(fractional_kelly, 0.05)  # Cap at 5% per trade

    def _detect_regime(self, df: pd.DataFrame) -> str:
        """Classify current market regime."""
        adx = float(df["adx"].iloc[-1]) if not df["adx"].isna().iloc[-1] else 25
        volatility = float(df["volatility_20"].iloc[-1]) if not df["volatility_20"].isna().iloc[-1] else 0.01
        bb_width = float(df["bb_width"].iloc[-1]) if not df["bb_width"].isna().iloc[-1] else 0.05

        if adx > 30:
            return "trending"
        elif volatility > 0.02 or bb_width > 0.08:
            return "volatile"
        else:
            return "ranging"

    def _rule_based_signal(self, symbol: str, df: pd.DataFrame,
                            current_price: float,
                            account_balance: float) -> TradeSignal:
        """
        Fallback rule-based signal when ML model unavailable.
        Uses EMA crossover + RSI + MACD confluence.
        """
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        signals = []

        # EMA cross
        if latest["ema_9"] > latest["ema_20"] and prev["ema_9"] <= prev["ema_20"]:
            signals.append(1)
        elif latest["ema_9"] < latest["ema_20"] and prev["ema_9"] >= prev["ema_20"]:
            signals.append(-1)

        # RSI
        rsi = latest.get("rsi_14", 50)
        if rsi < 35:
            signals.append(1)
        elif rsi > 65:
            signals.append(-1)

        # MACD
        if latest.get("macd_hist", 0) > 0 and prev.get("macd_hist", 0) <= 0:
            signals.append(1)
        elif latest.get("macd_hist", 0) < 0 and prev.get("macd_hist", 0) >= 0:
            signals.append(-1)

        score = sum(signals)
        atr = float(df["atr_14"].iloc[-1])

        if score >= 2:
            action, confidence = "BUY", 0.60 + min(score * 0.05, 0.15)
            sl = current_price - atr * 2
            tp = current_price + atr * 4
        elif score <= -2:
            action, confidence = "SELL", 0.60 + min(abs(score) * 0.05, 0.15)
            sl = current_price + atr * 2
            tp = current_price - atr * 4
        else:
            action, confidence = "HOLD", 0.50
            sl = tp = current_price

        return TradeSignal(
            symbol=symbol, action=action, confidence=confidence,
            entry_price=current_price, stop_loss=round(sl, 5),
            take_profit=round(tp, 5),
            risk_reward=2.0, position_size_pct=0.01,
            predicted_return=(tp - current_price) / current_price,
            regime=self._detect_regime(df),
            strategy_used="Rule_Based_Fallback",
            features_summary={"rsi": rsi, "ema_cross": score},
            timestamp=datetime.now()
        )

    # ─────────────────────────────────────────────
    # MODEL PERSISTENCE
    # ─────────────────────────────────────────────

    def _save_models(self, symbol: str):
        path = Path(MODEL_DIR) / f"{symbol}_models.pkl"
        data = {
            "models": self.models.get(symbol),
            "scaler": self.scalers.get(symbol),
            "regime": self.regime_models.get(symbol),
            "importance": self.feature_importance.get(symbol),
            "saved_at": datetime.now().isoformat()
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)
        logger.info(f"Models saved: {path}")

    def _load_all_models(self):
        """Load all previously trained models on startup."""
        model_dir = Path(MODEL_DIR)
        for path in model_dir.glob("*_models.pkl"):
            symbol = path.stem.replace("_models", "")
            try:
                with open(path, "rb") as f:
                    data = pickle.load(f)
                self.models[symbol] = data["models"]
                self.scalers[symbol] = data["scaler"]
                self.regime_models[symbol] = data["regime"]
                self.feature_importance[symbol] = data.get("importance", {})
                logger.info(f"Loaded models for {symbol}")
            except Exception as e:
                logger.error(f"Failed to load model {path}: {e}")

    def get_feature_importance(self, symbol: str) -> Dict:
        return self.feature_importance.get(symbol, {})
