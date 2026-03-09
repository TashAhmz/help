# ⚡ APEX TRADING SYSTEM

> Automated ML-powered commodity trading for Gold, Silver, Crude Oil, Natural Gas & Low Carbon markets via Vantage Markets REST API.

---

## 🏗️ Architecture

```
apex_trading/
├── main.py                    ← Entry point
├── requirements.txt
├── config/
│   └── config.py              ← All settings (API keys, markets, risk params)
├── core/
│   ├── vantage_api.py         ← Vantage REST API connector
│   ├── trading_engine.py      ← Main trading loop orchestrator
│   └── risk_manager.py        ← Risk controls & position sizing
├── ml/
│   ├── ml_engine.py           ← Ensemble ML (RF + GB + XGBoost)
│   └── models/                ← Saved trained models (auto-created)
├── data/
│   └── data_fetcher.py        ← OHLCV + fundamentals + news sentiment
├── dashboard/
│   └── dashboard.py           ← PyQt6 desktop dashboard
├── email_reports/
│   └── email_reporter.py      ← Daily/weekly HTML email reports
├── firebase/
│   └── firebase_db.py         ← Firebase Realtime Database sync
└── logs/                      ← Auto-created log files
```

---

## 🚀 Quick Start

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API credentials
Edit `config/config.py`:

```python
# Vantage Markets
VANTAGE_API_KEY    = "your_key"
VANTAGE_API_SECRET = "your_secret"
VANTAGE_BASE_URL   = "https://api.vantagemarkets.com/v1"  # Confirm with Vantage

# Email
EMAIL_SENDER   = "your@gmail.com"
EMAIL_PASSWORD = "your_gmail_app_password"  # Enable 2FA → App Passwords

# Firebase (optional but recommended)
# See firebase/firebase_db.py for setup guide
```

### 3. Launch
```bash
# Full system (engine + dashboard)
python main.py

# Dashboard demo only (no API needed)
python main.py --dashboard

# Train ML models first
python main.py --train

# Headless engine only (server/VPS)
python main.py --engine

# Setup guide
python main.py --setup
```

---

## 🤖 ML Engine

The system uses a **3-model ensemble**:

| Model | Strength | Weight |
|-------|----------|--------|
| Random Forest | Non-linear trend patterns | 25% |
| Gradient Boosting | Momentum detection | 25% |
| XGBoost | Complex regime patterns | 50% |

**Features used (50+):**
- Moving averages (SMA/EMA: 9, 20, 50, 100, 200)
- RSI (14, 21), MACD, Stochastic, Williams %R, ADX
- Bollinger Bands (width + position)
- ATR-based volatility
- OBV volume analysis
- Candle pattern features
- EIA oil inventory data (for energy markets)
- News sentiment (via NewsAPI + TextBlob)
- Economic calendar proximity (FOMC, OPEC, NFP, EIA reports)

**Position sizing:** Kelly Criterion (50% fractional) adjusted by confidence score

**Signal threshold:** Minimum 65% ML confidence to place a trade

---

## 📊 Markets Traded

### Primary (main focus)
| Symbol | Market | Category |
|--------|--------|----------|
| USOIL  | Crude Oil WTI | Energy |
| UKOIL  | Crude Oil Brent | Energy |
| XAUUSD | Gold/USD | Metals |
| XAGUSD | Silver/USD | Metals |
| NGAS   | Natural Gas | Energy |
| HEAT   | Heating Oil | Energy |
| RBOB   | RBOB Gasoline | Energy |

### Secondary (low carbon, side focus)
| Symbol | Market |
|--------|--------|
| CARBON | Carbon Credits |
| ETHUSD | Ethanol (proxy) |

---

## ⚙️ Risk Management

- **Max daily drawdown:** 5% — auto-halts all trading if breached
- **Max open positions:** 8 simultaneous
- **Position sizing:** Dynamic (Kelly Criterion via ML)
- **Stop losses:** ATR-based, tightened by confidence
- **Take profits:** Minimum 2:1 R:R ratio
- **Trailing stops:** Automatically trails profitable positions
- **Mode switch:** Paper ↔ Live toggle in dashboard

---

## 📧 Email Reports

Reports sent to:
- josephhyland10@icloud.com
- tashifkarim@gmail.com

**Daily report** (6:00 PM): P&L, trades executed, open positions, news highlights
**Weekly report** (Friday 6:30 PM): Weekly P&L, win rate, best trades, per-market breakdown

---

## 🔥 Firebase Real-Time Database

All data synced live:
```
/positions/{symbol}     → Live open positions
/portfolio/live         → Current equity + P&L
/trade_history          → All completed trades
/pnl_history/{date}     → Daily P&L records
/signals_log            → All ML signals (for analysis)
/ml_metrics/{symbol}    → Model performance
/system_log             → System events
```

---

## ⚠️ Important Notes

1. **Start in paper trading mode** — monitor for at least 2-4 weeks
2. **Verify Vantage API endpoint** — confirm the exact REST API URL with Vantage
3. **Backtest before going live** — use `--train` to train models first
4. **This is not financial advice** — trade at your own risk
5. **ML models retrain every 24 hours** automatically

---

## 📞 Support

Built by APEX Team. Configure all API keys in `config/config.py` before first run.
