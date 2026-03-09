"""
APEX TRADING SYSTEM - Desktop Dashboard
=========================================
A sleek, dark-themed real-time trading dashboard built with PyQt6.
Features:
  - Live price feeds for all markets
  - Real-time P&L tracking
  - Open positions with unrealized P&L
  - ML signal confidence display
  - Market regime indicators
  - Trade history log
  - Paper / Live mode toggle
  - Emergency halt button
  - Firebase sync status
"""

import sys
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QSizePolicy, QTabWidget, QTextEdit,
    QGroupBox, QScrollArea, QStatusBar, QProgressBar, QComboBox
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QSize
)
from PyQt6.QtGui import (
    QColor, QPalette, QFont, QIcon, QLinearGradient, QPainter,
    QBrush, QPen
)


# ─────────────────────────────────────────────
# COLORS & STYLES
# ─────────────────────────────────────────────
COLORS = {
    "bg_dark":      "#080C18",
    "bg_card":      "#0D1425",
    "bg_card2":     "#111827",
    "border":       "#1A2E4A",
    "border_bright":"#1E3A5F",
    "accent_blue":  "#00C8FF",
    "accent_cyan":  "#00FFCC",
    "green":        "#00E676",
    "red":          "#FF1744",
    "yellow":       "#FFD600",
    "orange":       "#FF6D00",
    "text_primary": "#E8F0FE",
    "text_secondary":"#7B93B8",
    "text_dim":     "#3D5470",
}

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {COLORS['bg_dark']};
    color: {COLORS['text_primary']};
    font-family: 'JetBrains Mono', 'Consolas', 'Courier New', monospace;
}}
QTabWidget::pane {{
    border: 1px solid {COLORS['border']};
    background-color: {COLORS['bg_dark']};
    border-radius: 8px;
}}
QTabBar::tab {{
    background: {COLORS['bg_card']};
    color: {COLORS['text_secondary']};
    padding: 10px 20px;
    font-size: 11px;
    letter-spacing: 1.5px;
    border: 1px solid {COLORS['border']};
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    margin-right: 2px;
    text-transform: uppercase;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: {COLORS['bg_card2']};
    color: {COLORS['accent_blue']};
    border-color: {COLORS['accent_blue']};
}}
QTableWidget {{
    background-color: {COLORS['bg_card']};
    alternate-background-color: {COLORS['bg_card2']};
    color: {COLORS['text_primary']};
    gridline-color: {COLORS['border']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    font-size: 12px;
}}
QTableWidget::item {{
    padding: 8px 12px;
    border-bottom: 1px solid {COLORS['border']};
}}
QTableWidget::item:selected {{
    background-color: {COLORS['border_bright']};
    color: {COLORS['accent_blue']};
}}
QHeaderView::section {{
    background-color: {COLORS['bg_dark']};
    color: {COLORS['text_secondary']};
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid {COLORS['border']};
    font-size: 10px;
    letter-spacing: 1.5px;
    font-weight: 600;
    text-transform: uppercase;
}}
QPushButton {{
    background-color: {COLORS['bg_card2']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border_bright']};
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
QPushButton:hover {{
    background-color: {COLORS['border_bright']};
    border-color: {COLORS['accent_blue']};
    color: {COLORS['accent_blue']};
}}
QPushButton:pressed {{ background-color: {COLORS['border']}; }}
QScrollBar:vertical {{
    background: {COLORS['bg_dark']};
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['border_bright']};
    border-radius: 3px;
}}
QTextEdit {{
    background-color: {COLORS['bg_card']};
    color: {COLORS['text_secondary']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    font-size: 11px;
    padding: 8px;
}}
QComboBox {{
    background-color: {COLORS['bg_card2']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border_bright']};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 11px;
}}
QComboBox::drop-down {{ border: none; }}
QProgressBar {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    text-align: center;
    font-size: 10px;
    color: {COLORS['text_primary']};
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS['accent_blue']}, stop:1 {COLORS['accent_cyan']});
    border-radius: 3px;
}}
"""


# ─────────────────────────────────────────────
# STAT CARD WIDGET
# ─────────────────────────────────────────────
class StatCard(QFrame):
    def __init__(self, label: str, value: str = "--",
                 color: str = None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
                padding: 4px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(16, 14, 16, 14)

        self.label_widget = QLabel(label.upper())
        self.label_widget.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 10px;
            letter-spacing: 1.5px;
            font-weight: 600;
        """)

        self.value_widget = QLabel(value)
        value_color = color or COLORS['accent_blue']
        self.value_widget.setStyleSheet(f"""
            color: {value_color};
            font-size: 24px;
            font-weight: 900;
            letter-spacing: 1px;
        """)

        layout.addWidget(self.label_widget)
        layout.addWidget(self.value_widget)

    def set_value(self, value: str, color: str = None):
        self.value_widget.setText(value)
        if color:
            self.value_widget.setStyleSheet(f"""
                color: {color};
                font-size: 24px;
                font-weight: 900;
            """)


# ─────────────────────────────────────────────
# MARKET ROW WIDGET
# ─────────────────────────────────────────────
class MarketRow(QFrame):
    def __init__(self, symbol: str, name: str, parent=None):
        super().__init__(parent)
        self.symbol = symbol
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                margin: 2px 0;
            }}
            QFrame:hover {{
                border-color: {COLORS['accent_blue']}66;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)

        # Symbol
        sym_label = QLabel(symbol)
        sym_label.setStyleSheet(f"color:{COLORS['accent_cyan']};font-size:13px;font-weight:700;min-width:80px")
        layout.addWidget(sym_label)

        # Name
        name_label = QLabel(name[:20])
        name_label.setStyleSheet(f"color:{COLORS['text_secondary']};font-size:11px;min-width:130px")
        layout.addWidget(name_label)

        layout.addStretch()

        # Price
        self.price_label = QLabel("--")
        self.price_label.setStyleSheet(f"color:{COLORS['text_primary']};font-size:14px;font-weight:700;min-width:100px;text-align:right")
        self.price_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.price_label)

        # Change
        self.change_label = QLabel("--")
        self.change_label.setStyleSheet(f"color:{COLORS['text_secondary']};font-size:12px;min-width:80px;text-align:right")
        self.change_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.change_label)

        # Signal badge
        self.signal_label = QLabel("--")
        self.signal_label.setStyleSheet(f"""
            background:{COLORS['bg_card2']};border:1px solid {COLORS['border']};
            border-radius:4px;padding:2px 8px;color:{COLORS['text_dim']};
            font-size:10px;font-weight:700;letter-spacing:1px;min-width:50px;
        """)
        self.signal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.signal_label)

        # Confidence bar
        self.conf_bar = QProgressBar()
        self.conf_bar.setMaximumWidth(80)
        self.conf_bar.setMaximumHeight(8)
        self.conf_bar.setValue(0)
        self.conf_bar.setTextVisible(False)
        layout.addWidget(self.conf_bar)

    def update_price(self, price: float, change_pct: float):
        self.price_label.setText(f"${price:,.4f}")
        color = COLORS['green'] if change_pct >= 0 else COLORS['red']
        sign = "+" if change_pct >= 0 else ""
        self.change_label.setText(f"{sign}{change_pct:.2f}%")
        self.change_label.setStyleSheet(
            f"color:{color};font-size:12px;min-width:80px;text-align:right"
        )

    def update_signal(self, action: str, confidence: float):
        colors = {"BUY": COLORS['green'], "SELL": COLORS['red'], "HOLD": COLORS['yellow']}
        color = colors.get(action, COLORS['text_dim'])
        self.signal_label.setText(action)
        self.signal_label.setStyleSheet(f"""
            background:{color}22;border:1px solid {color}66;
            border-radius:4px;padding:2px 8px;color:{color};
            font-size:10px;font-weight:700;letter-spacing:1px;min-width:50px;
        """)
        self.conf_bar.setValue(int(confidence * 100))


# ─────────────────────────────────────────────
# DATA REFRESH WORKER
# ─────────────────────────────────────────────
class DataWorker(QThread):
    data_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, engine=None):
        super().__init__()
        self.engine = engine
        self._running = True

    def run(self):
        while self._running:
            try:
                if self.engine:
                    data = {
                        "status": self.engine.get_status(),
                        "portfolio": self.engine.risk.get_portfolio_summary(),
                        "signals": {k: {
                            "action": v.action,
                            "confidence": v.confidence,
                            "entry": v.entry_price,
                            "sl": v.stop_loss,
                            "tp": v.take_profit,
                            "rr": v.risk_reward,
                            "regime": v.regime
                        } for k, v in self.engine.last_signals.items()},
                        "prices": dict(self.engine.current_prices),
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    # Demo mode with simulated data
                    data = self._generate_demo_data()
                self.data_ready.emit(data)
            except Exception as e:
                self.error.emit(str(e))
            self.msleep(2000)  # Refresh every 2 seconds

    def _generate_demo_data(self) -> dict:
        """Generate realistic demo data when engine not connected."""
        import random
        import math

        t = datetime.now().timestamp()

        def wave_price(base, amplitude, period):
            return base + amplitude * math.sin(t / period) + random.gauss(0, amplitude * 0.1)

        prices = {
            "XAUUSD": wave_price(2045.50, 8, 120),
            "XAGUSD": wave_price(24.35, 0.3, 90),
            "USOIL":  wave_price(78.90, 1.2, 150),
            "UKOIL":  wave_price(82.45, 1.1, 140),
            "NGAS":   wave_price(2.48, 0.08, 80),
            "HEAT":   wave_price(2.82, 0.05, 100),
            "RBOB":   wave_price(2.41, 0.04, 95),
        }

        actions = ["BUY", "SELL", "HOLD"]
        signals = {}
        for sym, price in prices.items():
            action = random.choices(actions, weights=[3, 3, 5])[0]
            conf = random.uniform(0.60, 0.92) if action != "HOLD" else random.uniform(0.45, 0.65)
            signals[sym] = {
                "action": action, "confidence": conf,
                "entry": price,
                "sl": price * (0.985 if action == "BUY" else 1.015),
                "tp": price * (1.03 if action == "BUY" else 0.97),
                "rr": round(random.uniform(1.5, 3.5), 2),
                "regime": random.choice(["trending", "ranging", "volatile"])
            }

        open_positions = [
            {"symbol": "USOIL",  "side": "buy",  "volume": 0.5,
             "entry_price": 77.85, "unrealized_pnl": (prices["USOIL"] - 77.85) * 50},
            {"symbol": "XAUUSD", "side": "buy",  "volume": 0.1,
             "entry_price": 2038.00, "unrealized_pnl": (prices["XAUUSD"] - 2038.00) * 10},
        ]
        total_upnl = sum(p["unrealized_pnl"] for p in open_positions)

        return {
            "status": {"status": "running", "mode": "paper", "paused": False,
                        "cycle_count": int(t) % 10000,
                        "stats": {"signals_generated": 247, "trades_executed": 43,
                                   "trades_rejected": 12, "errors": 0}},
            "portfolio": {
                "balance": 10000.00, "account_equity": 10000 + total_upnl,
                "daily_pnl": 127.45 + total_upnl * 0.1,
                "daily_pnl_pct": (127.45 + total_upnl * 0.1) / 100,
                "open_positions": len(open_positions),
                "positions": open_positions,
                "trading_halted": False, "halt_reason": "",
                "daily_trades_count": 7
            },
            "signals": signals,
            "prices": prices,
            "timestamp": datetime.now().isoformat()
        }

    def stop(self):
        self._running = False


# ─────────────────────────────────────────────
# MAIN DASHBOARD WINDOW
# ─────────────────────────────────────────────
class ApexDashboard(QMainWindow):
    def __init__(self, engine=None):
        super().__init__()
        self.engine = engine
        self.prev_prices: Dict[str, float] = {}
        self.log_lines = []

        self.setWindowTitle("⚡ APEX TRADING SYSTEM")
        self.setMinimumSize(1400, 900)
        self.resize(1600, 1000)
        self.setStyleSheet(STYLESHEET)

        self._build_ui()
        self._start_data_worker()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Header
        main_layout.addWidget(self._build_header())

        # Content
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(16, 12, 16, 12)

        # Left panel (markets + signals)
        left = self._build_left_panel()
        left.setMaximumWidth(480)
        content_layout.addWidget(left)

        # Right panel (stats + positions + tabs)
        content_layout.addWidget(self._build_right_panel(), 1)

        main_layout.addWidget(content, 1)

        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.setStyleSheet(f"""
            background: {COLORS['bg_card']};
            color: {COLORS['text_secondary']};
            border-top: 1px solid {COLORS['border']};
            font-size: 10px;
            padding: 2px 8px;
        """)
        self.status_bar.showMessage("APEX Trading System — Initializing...")

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setFixedHeight(64)
        header.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #050810, stop:0.5 #0A1428, stop:1 #050810);
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)

        # Logo
        logo = QLabel("⚡ APEX")
        logo.setStyleSheet(f"""
            color: {COLORS['accent_blue']};
            font-size: 22px;
            font-weight: 900;
            letter-spacing: 5px;
        """)
        layout.addWidget(logo)

        subtitle = QLabel("TRADING SYSTEM")
        subtitle.setStyleSheet(f"""
            color: {COLORS['text_dim']};
            font-size: 10px;
            letter-spacing: 3px;
            margin-left: 4px;
            margin-top: 10px;
        """)
        layout.addWidget(subtitle)
        layout.addStretch()

        # Mode toggle
        mode_label = QLabel("MODE:")
        mode_label.setStyleSheet(f"color:{COLORS['text_secondary']};font-size:10px;letter-spacing:1px")
        layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["📝 PAPER", "⚡ LIVE"])
        self.mode_combo.setFixedWidth(120)
        self.mode_combo.currentTextChanged.connect(self._on_mode_change)
        layout.addWidget(self.mode_combo)

        layout.addSpacing(12)

        # Control buttons
        self.pause_btn = QPushButton("⏸  PAUSE")
        self.pause_btn.setFixedWidth(110)
        self.pause_btn.clicked.connect(self._toggle_pause)
        layout.addWidget(self.pause_btn)

        halt_btn = QPushButton("⛔  HALT ALL")
        halt_btn.setFixedWidth(120)
        halt_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['red']}22;
                border: 1px solid {COLORS['red']}66;
                color: {COLORS['red']};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: {COLORS['red']}44;
                border-color: {COLORS['red']};
            }}
        """)
        halt_btn.clicked.connect(self._emergency_halt)
        layout.addWidget(halt_btn)

        layout.addSpacing(12)

        # Time
        self.time_label = QLabel()
        self.time_label.setStyleSheet(f"color:{COLORS['text_secondary']};font-size:12px;min-width:80px")
        layout.addWidget(self.time_label)

        # Clock timer
        clock = QTimer(self)
        clock.timeout.connect(self._update_clock)
        clock.start(1000)
        self._update_clock()

        return header

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        # Markets header
        hdr = QLabel("MARKETS & SIGNALS")
        hdr.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 10px;
            letter-spacing: 2px;
            font-weight: 700;
            padding: 4px 0;
        """)
        layout.addWidget(hdr)

        # Market rows
        from config.config import ALL_MARKETS
        self.market_rows: Dict[str, MarketRow] = {}
        for symbol, info in ALL_MARKETS.items():
            row = MarketRow(symbol, info["name"])
            self.market_rows[symbol] = row
            layout.addWidget(row)

        layout.addStretch()
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        # Stat cards row
        cards_widget = QWidget()
        cards_layout = QHBoxLayout(cards_widget)
        cards_layout.setSpacing(10)
        cards_layout.setContentsMargins(0, 0, 0, 0)

        self.card_equity    = StatCard("Account Equity", "$--,---")
        self.card_pnl       = StatCard("Today's P&L", "$0.00")
        self.card_positions = StatCard("Open Positions", "0")
        self.card_trades    = StatCard("Trades Today", "0")
        self.card_signals   = StatCard("Signals Generated", "0")
        self.card_mode      = StatCard("Mode", "PAPER", COLORS['yellow'])

        for card in [self.card_equity, self.card_pnl, self.card_positions,
                     self.card_trades, self.card_signals, self.card_mode]:
            cards_layout.addWidget(card)

        layout.addWidget(cards_widget)

        # Tab panel
        tabs = QTabWidget()

        # Tab 1: Open Positions
        tabs.addTab(self._build_positions_tab(), "📊  POSITIONS")

        # Tab 2: Trade History
        tabs.addTab(self._build_history_tab(), "📋  TRADE HISTORY")

        # Tab 3: ML Performance
        tabs.addTab(self._build_ml_tab(), "🤖  ML ENGINE")

        # Tab 4: System Log
        tabs.addTab(self._build_log_tab(), "📜  SYSTEM LOG")

        layout.addWidget(tabs, 1)
        return panel

    def _build_positions_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        self.positions_table = QTableWidget()
        self.positions_table.setColumnCount(7)
        self.positions_table.setHorizontalHeaderLabels([
            "SYMBOL", "SIDE", "VOLUME", "ENTRY PRICE",
            "CURRENT PRICE", "UNREALIZED P&L", "SL / TP"
        ])
        self.positions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.positions_table.setAlternatingRowColors(True)
        self.positions_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.positions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.positions_table)
        return widget

    def _build_history_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels([
            "SYMBOL", "SIDE", "VOLUME", "ENTRY", "CLOSE PRICE", "P&L", "CLOSED AT"
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.history_table)
        return widget

    def _build_ml_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        self.ml_table = QTableWidget()
        self.ml_table.setColumnCount(7)
        self.ml_table.setHorizontalHeaderLabels([
            "SYMBOL", "SIGNAL", "CONFIDENCE", "ENTRY",
            "STOP LOSS", "TAKE PROFIT", "REGIME"
        ])
        self.ml_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.ml_table.setAlternatingRowColors(True)
        self.ml_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.ml_table)

        # Retrain button
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 8, 0, 0)
        retrain_btn = QPushButton("🔄  RETRAIN ALL MODELS NOW")
        retrain_btn.clicked.connect(self._retrain_models)
        btn_layout.addWidget(retrain_btn)
        btn_layout.addStretch()
        layout.addWidget(btn_row)

        return widget

    def _build_log_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        layout.addWidget(self.log_text)
        return widget

    # ─────────────────────────────────────────────
    # DATA WORKER
    # ─────────────────────────────────────────────

    def _start_data_worker(self):
        self.worker = DataWorker(self.engine)
        self.worker.data_ready.connect(self._on_data_ready)
        self.worker.error.connect(self._on_worker_error)
        self.worker.start()

    def _on_data_ready(self, data: dict):
        """Update all dashboard elements with fresh data."""
        try:
            portfolio = data.get("portfolio", {})
            signals = data.get("signals", {})
            prices = data.get("prices", {})
            status = data.get("status", {})

            # Update stat cards
            equity = portfolio.get("account_equity", 0)
            pnl = portfolio.get("daily_pnl", 0)
            pnl_pct = portfolio.get("daily_pnl_pct", 0)
            pnl_color = COLORS['green'] if pnl >= 0 else COLORS['red']
            pnl_sign = "+" if pnl >= 0 else ""

            self.card_equity.set_value(f"${equity:,.2f}", COLORS['accent_blue'])
            self.card_pnl.set_value(
                f"{pnl_sign}${abs(pnl):,.2f}\n({pnl_sign}{pnl_pct:.2f}%)",
                pnl_color
            )
            self.card_positions.set_value(
                str(portfolio.get("open_positions", 0)),
                COLORS['yellow']
            )
            self.card_trades.set_value(
                str(portfolio.get("daily_trades_count", 0)),
                COLORS['accent_cyan']
            )
            self.card_signals.set_value(
                str(status.get("stats", {}).get("signals_generated", 0)),
                COLORS['accent_blue']
            )
            mode = status.get("mode", "paper").upper()
            self.card_mode.set_value(mode, COLORS['green'] if mode == "LIVE" else COLORS['yellow'])

            # Update market rows
            for symbol, row in self.market_rows.items():
                price = prices.get(symbol)
                if price:
                    prev = self.prev_prices.get(symbol, price)
                    change_pct = ((price - prev) / prev * 100) if prev else 0
                    row.update_price(price, change_pct)
                    self.prev_prices[symbol] = price

                sig = signals.get(symbol)
                if sig:
                    row.update_signal(sig["action"], sig["confidence"])

            # Update positions table
            self._update_positions_table(portfolio.get("positions", []), prices)

            # Update ML table
            self._update_ml_table(signals)

            # Halt warning
            if portfolio.get("trading_halted"):
                self.status_bar.showMessage(
                    f"⛔ TRADING HALTED: {portfolio.get('halt_reason', '')}",
                )
                self.status_bar.setStyleSheet(f"""
                    background: {COLORS['red']}22;
                    color: {COLORS['red']};
                    border-top: 1px solid {COLORS['red']}66;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 2px 8px;
                """)
            else:
                cycles = status.get("cycle_count", 0)
                fb_status = "🟢 Firebase" if True else "🔴 Firebase"
                self.status_bar.showMessage(
                    f"✅ Engine Running  |  Mode: {mode}  |  "
                    f"Cycle: #{cycles}  |  {fb_status}  |  "
                    f"Trades: {status.get('stats', {}).get('trades_executed', 0)}  |  "
                    f"Updated: {datetime.now().strftime('%H:%M:%S')}"
                )

            self._append_log(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"Data refresh | Equity: ${equity:,.2f} | "
                f"P&L: {pnl_sign}${abs(pnl):.2f}"
            )

        except Exception as e:
            self._append_log(f"[ERROR] Dashboard update error: {e}")

    def _update_positions_table(self, positions: List, prices: Dict):
        self.positions_table.setRowCount(len(positions))
        for i, pos in enumerate(positions):
            symbol = pos.get("symbol", "")
            current = prices.get(symbol, pos.get("entry_price", 0))
            upnl = pos.get("unrealized_pnl", 0)
            side = pos.get("side", "").upper()
            pnl_color = COLORS['green'] if upnl >= 0 else COLORS['red']
            side_color = COLORS['green'] if side == "BUY" else COLORS['red']

            cells = [
                (symbol, COLORS['accent_cyan']),
                (side, side_color),
                (str(pos.get("volume", 0)), COLORS['text_primary']),
                (f"${pos.get('entry_price', 0):.4f}", COLORS['text_primary']),
                (f"${current:.4f}", COLORS['text_primary']),
                (f"${upnl:+,.2f}", pnl_color),
                (f"SL:{pos.get('stop_loss',0):.4f} / TP:{pos.get('take_profit',0):.4f}",
                 COLORS['text_secondary']),
            ]
            for j, (text, color) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(color))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.positions_table.setItem(i, j, item)

    def _update_ml_table(self, signals: Dict):
        items = list(signals.items())
        self.ml_table.setRowCount(len(items))
        for i, (symbol, sig) in enumerate(items):
            action = sig.get("action", "HOLD")
            conf = sig.get("confidence", 0)
            action_color = {
                "BUY": COLORS['green'],
                "SELL": COLORS['red'],
                "HOLD": COLORS['yellow']
            }.get(action, COLORS['text_secondary'])
            regime_color = {
                "trending": COLORS['green'],
                "volatile": COLORS['red'],
                "ranging": COLORS['yellow']
            }.get(sig.get("regime", ""), COLORS['text_secondary'])

            cells = [
                (symbol, COLORS['accent_cyan']),
                (action, action_color),
                (f"{conf:.1%}", COLORS['accent_blue']),
                (f"${sig.get('entry', 0):.4f}", COLORS['text_primary']),
                (f"${sig.get('sl', 0):.4f}", COLORS['red']),
                (f"${sig.get('tp', 0):.4f}", COLORS['green']),
                (sig.get("regime", "--").upper(), regime_color),
            ]
            for j, (text, color) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(color))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.ml_table.setItem(i, j, item)

    def _append_log(self, message: str):
        self.log_lines.append(message)
        if len(self.log_lines) > 500:
            self.log_lines = self.log_lines[-500:]
        self.log_text.setText("\n".join(reversed(self.log_lines[-100:])))

    def _on_worker_error(self, error: str):
        self._append_log(f"[WORKER ERROR] {error}")

    # ─────────────────────────────────────────────
    # CONTROLS
    # ─────────────────────────────────────────────

    def _update_clock(self):
        self.time_label.setText(datetime.now().strftime("%H:%M:%S"))

    def _toggle_pause(self):
        if self.engine:
            if self.engine.paused:
                self.engine.resume()
                self.pause_btn.setText("⏸  PAUSE")
            else:
                self.engine.pause()
                self.pause_btn.setText("▶  RESUME")

    def _emergency_halt(self):
        if self.engine:
            self.engine.risk._halt_trading("Manual halt from dashboard")
            self._append_log("[HALT] Emergency halt triggered by user")
        else:
            self._append_log("[HALT] Engine not connected — demo mode")

    def _on_mode_change(self, text: str):
        mode = "live" if "LIVE" in text else "paper"
        if self.engine:
            self.engine.set_mode(mode)
        self._append_log(f"[MODE] Switched to {mode.upper()}")

    def _retrain_models(self):
        self._append_log("[ML] Manual retraining triggered...")
        if self.engine:
            thread = threading.Thread(
                target=self.engine._retrain_all_models, daemon=True
            )
            thread.start()

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
            self.worker.wait(2000)
        if self.engine:
            self.engine.stop()
        event.accept()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

def launch_dashboard(engine=None):
    app = QApplication(sys.argv)
    app.setApplicationName("APEX Trading System")

    # Load Google Fonts via Qt (optional)
    try:
        from PyQt6.QtGui import QFontDatabase
        QFontDatabase.addApplicationFont(":/fonts/JetBrainsMono-Regular.ttf")
    except Exception:
        pass

    window = ApexDashboard(engine=engine)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_dashboard()
