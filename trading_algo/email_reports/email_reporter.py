"""
APEX TRADING SYSTEM - Email Reporter
======================================
Sends beautiful HTML email reports:
  - Daily P&L summary at 6pm
  - Weekly performance summary on Friday
  - Emergency alerts (drawdown halt, system errors)
  - Trade notifications (on open/close)
"""

import smtplib
import logging
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional
from config.config import (
    EMAIL_RECIPIENTS, EMAIL_SENDER, EMAIL_PASSWORD,
    SMTP_HOST, SMTP_PORT
)

logger = logging.getLogger(__name__)


class EmailReporter:
    """Sends formatted HTML email reports."""

    def __init__(self):
        self.recipients = EMAIL_RECIPIENTS
        self.sender = EMAIL_SENDER

    def _send(self, subject: str, html_body: str,
              recipients: List[str] = None) -> bool:
        """Send an HTML email."""
        if not recipients:
            recipients = self.recipients

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender
            msg["To"] = ", ".join(recipients)
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(self.sender, EMAIL_PASSWORD)
                server.sendmail(self.sender, recipients, msg.as_string())

            logger.info(f"Email sent: {subject} → {recipients}")
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error("Email auth failed. Check EMAIL_SENDER and EMAIL_PASSWORD in config.")
            return False
        except Exception as e:
            logger.error(f"Email send error: {e}")
            return False

    # ─────────────────────────────────────────────
    # DAILY REPORT
    # ─────────────────────────────────────────────

    def send_daily_report(self, portfolio: Dict, trades: List[Dict],
                           signals: List[Dict] = None,
                           news_highlights: List[str] = None) -> bool:
        """Send end-of-day P&L and performance email."""
        date_str = datetime.now().strftime("%A, %B %d %Y")
        pnl = portfolio.get("daily_pnl", 0)
        pnl_pct = portfolio.get("daily_pnl_pct", 0)
        pnl_color = "#00C851" if pnl >= 0 else "#FF4444"
        pnl_sign = "+" if pnl >= 0 else ""
        emoji = "📈" if pnl >= 0 else "📉"

        trades_html = self._build_trades_table(trades)
        news_html = self._build_news_section(news_highlights or [])
        open_pos_html = self._build_open_positions_table(
            portfolio.get("positions", [])
        )

        html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0a0e1a; color: #e0e6f0; margin: 0; padding: 0; }}
  .wrapper {{ max-width: 680px; margin: 0 auto; padding: 20px; }}
  .header {{ background: linear-gradient(135deg, #0f1629 0%, #1a2340 100%);
             border: 1px solid #1e3a5f; border-radius: 12px; padding: 30px; text-align: center; margin-bottom: 20px; }}
  .logo {{ font-size: 28px; font-weight: 900; letter-spacing: 4px; color: #00d4ff; }}
  .subtitle {{ color: #8899bb; font-size: 13px; margin-top: 4px; }}
  .date {{ color: #c0cce0; font-size: 14px; margin-top: 8px; }}
  .pnl-card {{ background: #0f1629; border: 1px solid {pnl_color}44;
               border-radius: 12px; padding: 25px; text-align: center; margin-bottom: 20px; }}
  .pnl-amount {{ font-size: 48px; font-weight: 900; color: {pnl_color}; margin: 10px 0; }}
  .pnl-pct {{ font-size: 20px; color: {pnl_color}; }}
  .pnl-label {{ color: #8899bb; font-size: 13px; text-transform: uppercase; letter-spacing: 2px; }}
  .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-bottom: 20px; }}
  .stat-card {{ background: #0f1629; border: 1px solid #1e3a5f; border-radius: 10px; padding: 16px; text-align: center; }}
  .stat-value {{ font-size: 22px; font-weight: 700; color: #00d4ff; }}
  .stat-label {{ font-size: 11px; color: #8899bb; text-transform: uppercase; letter-spacing: 1px; margin-top: 4px; }}
  .section {{ background: #0f1629; border: 1px solid #1e3a5f; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
  .section-title {{ font-size: 14px; font-weight: 700; color: #00d4ff; text-transform: uppercase;
                    letter-spacing: 2px; margin-bottom: 15px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #0a0e1a; color: #8899bb; font-size: 11px; text-transform: uppercase;
        letter-spacing: 1px; padding: 10px 12px; text-align: left; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #1e3a5f; font-size: 13px; }}
  tr:last-child td {{ border-bottom: none; }}
  .buy {{ color: #00C851; font-weight: 600; }}
  .sell {{ color: #FF4444; font-weight: 600; }}
  .positive {{ color: #00C851; }}
  .negative {{ color: #FF4444; }}
  .footer {{ text-align: center; color: #4a5568; font-size: 11px; margin-top: 20px; padding: 15px; }}
  .alert-bar {{ background: #FF444422; border: 1px solid #FF444466; border-radius: 8px;
                padding: 12px 16px; margin-bottom: 20px; color: #FF4444; font-size: 13px; }}
</style>
</head>
<body>
<div class="wrapper">

  <div class="header">
    <div class="logo">⚡ APEX</div>
    <div class="subtitle">TRADING SYSTEM — DAILY REPORT</div>
    <div class="date">{emoji} {date_str}</div>
  </div>

  <div class="pnl-card">
    <div class="pnl-label">Today's P&L</div>
    <div class="pnl-amount">{pnl_sign}${pnl:,.2f}</div>
    <div class="pnl-pct">{pnl_sign}{pnl_pct:.2f}%</div>
  </div>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-value">${portfolio.get('account_equity', 0):,.0f}</div>
      <div class="stat-label">Account Equity</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{portfolio.get('daily_trades_count', len(trades))}</div>
      <div class="stat-label">Trades Today</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{portfolio.get('open_positions', 0)}</div>
      <div class="stat-label">Open Positions</div>
    </div>
  </div>

  {trades_html}
  {open_pos_html}
  {news_html}

  <div class="footer">
    APEX Trading System · Automated Report<br>
    Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}<br>
    <span style="color: #2d3748">Risk disclaimer: Past performance is not indicative of future results.</span>
  </div>

</div>
</body>
</html>
"""
        subject = f"APEX | Daily Report {emoji} {pnl_sign}${abs(pnl):,.2f} | {date_str}"
        return self._send(subject, html)

    def send_weekly_report(self, weekly_stats: Dict,
                            daily_breakdown: List[Dict]) -> bool:
        """Send weekly performance summary every Friday."""
        week_pnl = weekly_stats.get("total_pnl", 0)
        pnl_color = "#00C851" if week_pnl >= 0 else "#FF4444"
        pnl_sign = "+" if week_pnl >= 0 else ""
        win_rate = weekly_stats.get("win_rate", 0) * 100

        days_html = ""
        for day in daily_breakdown:
            d_pnl = day.get("pnl", 0)
            d_color = "#00C851" if d_pnl >= 0 else "#FF4444"
            d_sign = "+" if d_pnl >= 0 else ""
            days_html += f"""
            <tr>
              <td>{day.get('date', '')}</td>
              <td>{day.get('trades', 0)}</td>
              <td class="{'positive' if d_pnl >= 0 else 'negative'}">{d_sign}${d_pnl:,.2f}</td>
              <td style="color:{d_color}">{d_sign}{day.get('pnl_pct', 0):.2f}%</td>
            </tr>"""

        html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0a0e1a; color: #e0e6f0; margin:0; padding:0; }}
  .wrapper {{ max-width: 680px; margin: 0 auto; padding: 20px; }}
  .header {{ background: linear-gradient(135deg, #0f1629, #1a2340); border: 1px solid #1e3a5f;
             border-radius: 12px; padding: 30px; text-align: center; margin-bottom: 20px; }}
  .logo {{ font-size: 28px; font-weight: 900; letter-spacing: 4px; color: #00d4ff; }}
  .pnl-card {{ background: #0f1629; border: 1px solid {pnl_color}44; border-radius: 12px;
               padding: 25px; text-align: center; margin-bottom: 20px; }}
  .pnl-amount {{ font-size: 52px; font-weight: 900; color: {pnl_color}; }}
  .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }}
  .stat-card {{ background: #0f1629; border: 1px solid #1e3a5f; border-radius: 10px;
                padding: 14px; text-align: center; }}
  .stat-value {{ font-size: 20px; font-weight: 700; color: #00d4ff; }}
  .stat-label {{ font-size: 10px; color: #8899bb; text-transform: uppercase; letter-spacing: 1px; }}
  .section {{ background: #0f1629; border: 1px solid #1e3a5f; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
  .section-title {{ font-size: 14px; font-weight: 700; color: #00d4ff; text-transform: uppercase;
                    letter-spacing: 2px; margin-bottom: 15px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #0a0e1a; color: #8899bb; font-size: 11px; padding: 10px 12px; text-align: left; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #1e3a5f; font-size: 13px; }}
  .positive {{ color: #00C851; }} .negative {{ color: #FF4444; }}
  .footer {{ text-align: center; color: #4a5568; font-size: 11px; margin-top: 20px; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <div class="logo">⚡ APEX</div>
    <div style="color:#8899bb;font-size:13px;margin-top:4px">WEEKLY PERFORMANCE REPORT</div>
    <div style="color:#c0cce0;font-size:14px;margin-top:8px">Week of {datetime.now().strftime('%B %d, %Y')}</div>
  </div>

  <div class="pnl-card">
    <div style="color:#8899bb;font-size:12px;text-transform:uppercase;letter-spacing:2px">Weekly P&L</div>
    <div class="pnl-amount">{pnl_sign}${abs(week_pnl):,.2f}</div>
    <div style="font-size:18px;color:{pnl_color}">{pnl_sign}{weekly_stats.get('pnl_pct', 0):.2f}%</div>
  </div>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-value">{weekly_stats.get('total_trades', 0)}</div>
      <div class="stat-label">Total Trades</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color:{'#00C851' if win_rate >= 50 else '#FF4444'}">{win_rate:.0f}%</div>
      <div class="stat-label">Win Rate</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{weekly_stats.get('best_trade', 0):+.0f}</div>
      <div class="stat-label">Best Trade $</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{weekly_stats.get('avg_rr', 0):.1f}x</div>
      <div class="stat-label">Avg R:R</div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">📅 Daily Breakdown</div>
    <table>
      <tr><th>Date</th><th>Trades</th><th>P&L</th><th>Return</th></tr>
      {days_html}
    </table>
  </div>

  <div class="section">
    <div class="section-title">🏆 Top Performing Markets</div>
    <table>
      <tr><th>Market</th><th>Trades</th><th>P&L</th><th>Win Rate</th></tr>
      {''.join(f"<tr><td>{m['symbol']}</td><td>{m['trades']}</td><td class='{'positive' if m['pnl']>=0 else 'negative'}'>${m['pnl']:,.2f}</td><td>{m['win_rate']*100:.0f}%</td></tr>" for m in weekly_stats.get('by_market', []))}
    </table>
  </div>

  <div class="footer">
    APEX Trading System · Weekly Report<br>
    {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
  </div>
</div>
</body>
</html>
"""
        subject = f"APEX | Weekly Report 📊 {pnl_sign}${abs(week_pnl):,.2f} | Win Rate {win_rate:.0f}%"
        return self._send(subject, html)

    def send_alert(self, alert_type: str, message: str, details: Dict = None) -> bool:
        """Send emergency/important alert immediately."""
        icons = {
            "halt": "⛔", "error": "🔴", "warning": "⚠️",
            "profit": "💰", "loss": "📉", "info": "ℹ️"
        }
        icon = icons.get(alert_type, "📢")
        color = "#FF4444" if alert_type in ["halt", "error", "loss"] else "#00C851"

        details_html = ""
        if details:
            rows = "".join(
                f"<tr><td style='color:#8899bb;padding:6px 12px'>{k}</td>"
                f"<td style='padding:6px 12px'>{v}</td></tr>"
                for k, v in details.items()
            )
            details_html = f"<table style='width:100%;border-collapse:collapse'>{rows}</table>"

        html = f"""
<!DOCTYPE html><html><head><style>
  body {{ font-family: Arial, sans-serif; background: #0a0e1a; color: #e0e6f0; margin:0; padding:20px; }}
  .card {{ max-width: 500px; margin: 0 auto; background: #0f1629; border: 2px solid {color}44;
           border-radius: 12px; padding: 25px; }}
  .icon {{ font-size: 40px; text-align: center; }}
  .title {{ font-size: 20px; font-weight: 700; color: {color}; text-align: center; margin: 10px 0; }}
  .msg {{ color: #c0cce0; font-size: 14px; text-align: center; margin: 10px 0 20px; }}
</style></head><body>
<div class="card">
  <div class="icon">{icon}</div>
  <div class="title">APEX ALERT: {alert_type.upper()}</div>
  <div class="msg">{message}</div>
  {details_html}
  <div style="text-align:center;color:#4a5568;font-size:11px;margin-top:15px">
    {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
  </div>
</div>
</body></html>
"""
        subject = f"APEX {icon} {alert_type.upper()}: {message[:60]}"
        return self._send(subject, html)

    # ─────────────────────────────────────────────
    # HTML HELPERS
    # ─────────────────────────────────────────────

    def _build_trades_table(self, trades: List[Dict]) -> str:
        if not trades:
            return """<div class="section">
              <div class="section-title">📋 Today's Trades</div>
              <p style="color:#4a5568;text-align:center;font-size:13px">No trades executed today.</p>
            </div>"""

        rows = ""
        for t in trades:
            profit = t.get("profit", 0)
            sign = "+" if profit >= 0 else ""
            css = "positive" if profit >= 0 else "negative"
            side_css = "buy" if t.get("side") == "buy" else "sell"
            rows += f"""
            <tr>
              <td><strong>{t.get('symbol','')}</strong></td>
              <td class="{side_css}">{t.get('side','').upper()}</td>
              <td>{t.get('volume', 0)}</td>
              <td>${t.get('entry_price', 0):.4f}</td>
              <td class="{css}">{sign}${profit:.2f}</td>
              <td style="color:#8899bb;font-size:11px">{t.get('closed_at','')[:16]}</td>
            </tr>"""

        return f"""
        <div class="section">
          <div class="section-title">📋 Today's Trades ({len(trades)})</div>
          <table>
            <tr><th>Symbol</th><th>Side</th><th>Volume</th><th>Entry</th><th>P&L</th><th>Time</th></tr>
            {rows}
          </table>
        </div>"""

    def _build_open_positions_table(self, positions: List[Dict]) -> str:
        if not positions:
            return ""
        rows = ""
        for p in positions:
            upnl = p.get("unrealized_pnl", 0)
            css = "positive" if upnl >= 0 else "negative"
            rows += f"""
            <tr>
              <td><strong>{p.get('symbol','')}</strong></td>
              <td class="{'buy' if p.get('side')=='buy' else 'sell'}">{p.get('side','').upper()}</td>
              <td>{p.get('volume', 0)}</td>
              <td>${p.get('entry_price', 0):.4f}</td>
              <td class="{css}">${upnl:+.2f}</td>
            </tr>"""

        return f"""
        <div class="section">
          <div class="section-title">🔓 Open Positions ({len(positions)})</div>
          <table>
            <tr><th>Symbol</th><th>Side</th><th>Volume</th><th>Entry</th><th>Unrealized P&L</th></tr>
            {rows}
          </table>
        </div>"""

    def _build_news_section(self, highlights: List[str]) -> str:
        if not highlights:
            return ""
        items = "".join(
            f"<li style='margin-bottom:8px;color:#c0cce0;font-size:13px'>{h}</li>"
            for h in highlights[:5]
        )
        return f"""
        <div class="section">
          <div class="section-title">📰 Market News Highlights</div>
          <ul style="margin:0;padding-left:18px">{items}</ul>
        </div>"""
