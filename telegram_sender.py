"""
Telegram Report Sender
======================
Sends hourly investment reports via Telegram Bot API.

Setup:
  1. Talk to @BotFather on Telegram
  2. Send /newbot → follow steps to create your bot
  3. Copy the Bot Token
  4. Send /start to your new bot
  5. Get your Chat ID (talk to @userinfobot or check API)
  6. Add to .env:
     TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
     TELEGRAM_CHAT_ID=123456789
"""

import json
import logging
import os
import re
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


def _esc(text) -> str:
    """
    Escape text for Telegram HTML parse_mode.
    Must escape &, <, > or the entire message gets rejected silently.
    """
    if text is None:
        return "N/A"
    text = str(text)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


class TelegramSender:
    """Sends investment reports to Telegram."""

    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.bot_token and self.chat_id)

        if self.enabled:
            me = self._api_call("getMe")
            if me:
                bot_name = me.get("result", {}).get("username", "unknown")
                logger.info(f"📱 Telegram bot connected: @{bot_name} → Chat {self.chat_id}")
            else:
                logger.warning("📱 Telegram bot token invalid.")
        else:
            logger.info("📱 Telegram not configured. Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env")

    # ── API Layer ──

    def _api_call(self, method: str, data: dict = None, files: dict = None) -> Optional[Dict]:
        if not self.bot_token:
            return None

        url = TELEGRAM_API_BASE.format(token=self.bot_token, method=method)

        try:
            if files:
                import mimetypes
                boundary = "----PyBoundary" + datetime.now().strftime("%Y%m%d%H%M%S%f")
                body = b""
                if data:
                    for key, value in data.items():
                        body += f"--{boundary}\r\n".encode()
                        body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
                        body += f"{value}\r\n".encode()
                for field_name, (_, file_name, file_content) in files.items():
                    mime = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
                    body += f"--{boundary}\r\n".encode()
                    body += f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"\r\n'.encode()
                    body += f"Content-Type: {mime}\r\n\r\n".encode()
                    body += file_content + b"\r\n"
                body += f"--{boundary}--\r\n".encode()
                req = urllib.request.Request(url, data=body, method="POST")
                req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

            elif data:
                req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), method="POST")
                req.add_header("Content-Type", "application/json")

            else:
                req = urllib.request.Request(url, method="GET")

            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if not result.get("ok"):
                    logger.error(f"📱 Telegram API error: {result.get('description', 'unknown')}")
                return result

        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            logger.error(f"📱 Telegram HTTP {e.code}: {err}")
            return None
        except Exception as e:
            logger.error(f"📱 Telegram call failed ({method}): {e}")
            return None

    # ── Send Methods ──

    def send_report(self, report: Dict) -> bool:
        """Send complete hourly report via Telegram."""
        if not self.enabled:
            logger.info("📱 Telegram not configured. Report saved locally only.")
            return False

        sent_any = False

        # 1) Summary
        try:
            msg = self._fmt_summary(report)
            if self._send_safe(msg):
                sent_any = True
        except Exception as e:
            logger.error(f"📱 Summary message failed: {e}")

        # 2) Per-stock deep analysis
        for ticker, sr in report.get("stock_reports", {}).items():
            try:
                msg = self._fmt_stock(ticker, sr)
                if self._send_safe(msg):
                    sent_any = True
            except Exception as e:
                logger.error(f"📱 Stock message {ticker} failed: {e}")

        # 3) "What Changed" review
        prev = report.get("prev_hour_review", {})
        if prev.get("reviews"):
            try:
                msg = self._fmt_review(prev)
                if self._send_safe(msg):
                    sent_any = True
            except Exception as e:
                logger.error(f"📱 Review message failed: {e}")

        # 4) HTML report as file
        html_path = "report_latest.html"
        if os.path.exists(html_path):
            try:
                with open(html_path, "rb") as f:
                    html_content = f.read()
                self._send_document(
                    file_name=f"report_{report['date']}_{report['time'].replace(':', '')}.html",
                    file_content=html_content,
                    caption=f"📄 Full Report — {report['date']} {report['time']}",
                )
            except Exception as e:
                logger.error(f"📱 Document send failed: {e}")

        if sent_any:
            logger.info(f"📱 Report sent to Telegram ({self.chat_id})")
        else:
            logger.error("📱 No messages were sent successfully!")
        return sent_any

    def _send_safe(self, text: str) -> bool:
        """
        Send a message with bulletproof retry logic.
        Try HTML → if fails, strip to plain text → if fails, log error.
        NEVER give up and skip remaining messages.
        """
        if not text or not text.strip():
            logger.warning("📱 Skipping empty message")
            return False

        chunks = self._split_message(text, max_len=4096)
        all_ok = True

        for i, chunk in enumerate(chunks):
            # Attempt 1: HTML mode
            ok = self._raw_send(chunk, parse_mode="HTML")

            # Attempt 2: Plain text fallback (every chunk, not just chunk 0)
            if not ok:
                plain = self._strip_html(chunk)
                logger.warning(f"📱 HTML failed for chunk {i+1}, retrying plain text...")
                ok = self._raw_send(plain, parse_mode=None)

            if not ok:
                logger.error(f"📱 Chunk {i+1}/{len(chunks)} failed completely. "
                           f"Preview: {chunk[:150]}")
                all_ok = False

        return all_ok

    def _raw_send(self, text: str, parse_mode: str = None) -> bool:
        """Low-level send. Returns True if OK."""
        data = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            data["parse_mode"] = parse_mode

        result = self._api_call("sendMessage", data=data)
        if result and result.get("ok"):
            return True
        return False

    def _send_document(self, file_name: str, file_content: bytes, caption: str = "") -> bool:
        data = {
            "chat_id": self.chat_id,
            "caption": caption[:1024],
        }
        files = {"document": (file_name, file_name, file_content)}
        result = self._api_call("sendDocument", data=data, files=files)
        if result and result.get("ok"):
            logger.info(f"📱 Document sent: {file_name}")
            return True
        return False

    # ── Formatting (ALL dynamic text goes through _esc()) ──

    def _fmt_summary(self, report: Dict) -> str:
        s = report.get("action_summary", {})
        prev = report.get("prev_hour_review", {})
        multi = report.get("multi_hour_review", {})
        e = _esc  # shortcut

        L = []
        L.append(f"🏦 <b>AI Investment Bank — Hourly Report #{report.get('cycle_number', '?')}</b>")
        L.append(f"📅 {e(report['date'])} {e(report['time'])} | Regime: {e(report['market_regime'])}")
        L.append(f"📊 {report.get('total_discovered', 0)} stocks scanned\n")

        # Stats
        be = "🟢" if s.get("total_buy", 0) > 0 else "⚪"
        se = "🔴" if s.get("total_sell", 0) > 0 else "⚪"
        L.append(f"{be} BUY: <b>{s.get('total_buy', 0)}</b>  |  "
                 f"{se} SELL: <b>{s.get('total_sell', 0)}</b>  |  "
                 f"🟡 HOLD: <b>{s.get('total_hold', 0)}</b>")

        # Prev hour
        if prev.get("reviews"):
            acc = prev.get("accuracy", 0)
            ae = "📈" if acc > 0.6 else "📉" if acc < 0.4 else "➡️"
            L.append(f"\n{ae} <b>Prev Hour:</b> {acc:.0%} "
                    f"({prev.get('correct_count', 0)}/{prev.get('total_count', 0)})\n"
                    f"   {e(prev.get('learning_notes', '')[:100])}")

        # Trend
        if multi.get("trend") and multi["trend"] != "no_data":
            te = "📈" if "IMPROV" in multi["trend"].upper() else "📉" if "DECLIN" in multi["trend"].upper() else "➡️"
            L.append(f"{te} <b>Trend:</b> {e(multi['trend'].upper())}")

        # BUY
        if s.get("buy_recommendations"):
            L.append(f"\n{'━'*20}\n🟢 <b>BUY RECOMMENDATIONS</b>\n{'━'*20}")
            for b in s["buy_recommendations"]:
                L.append(f"  <b>{e(b['ticker'])}</b> @ ${b['price']:.2f}")
                L.append(f"    Conf: {b['confidence']:.0%} | Risk: {e(b['risk'])}")
                if b.get("target"):
                    L.append(f"    🎯 Target: ${b['target']:.2f} | 🛑 Stop: ${b.get('stop_loss', 0):.2f}")
                L.append(f"    💡 {e(b['reasoning'][:200])}")

        # SELL
        if s.get("sell_recommendations"):
            L.append(f"\n{'━'*20}\n🔴 <b>SELL RECOMMENDATIONS</b>\n{'━'*20}")
            for sl in s["sell_recommendations"]:
                L.append(f"  <b>{e(sl['ticker'])}</b> @ ${sl['price']:.2f}")
                L.append(f"    💡 {e(sl['reasoning'][:200])}")

        # HOLD
        if s.get("hold_recommendations"):
            holds = ", ".join(e(h['ticker']) for h in s["hold_recommendations"])
            L.append(f"\n🟡 HOLD: {holds}")

        # Top 5
        ranking = report.get("ranking_table", [])[:5]
        if ranking:
            L.append(f"\n{'━'*20}\n🏆 <b>TOP 5</b>\n{'━'*20}")
            for r in ranking:
                ce = "🟢" if r["daily_change"] > 0 else "🔴"
                L.append(f"  {r['rank']}. <b>{e(r['ticker'])}</b> ${r['price']:.2f} "
                        f"{ce}{r['daily_change']:+.2f}% Sc:{r['score']:.0f} RSI:{r['rsi']:.0f}")

        L.append("\n⏱ Next report in ~60 min")
        L.append("⚠️ AI analysis — Not financial advice")
        return "\n".join(L)

    def _fmt_stock(self, ticker: str, sr: Dict) -> str:
        e = _esc
        dec = sr.get("ceo_decision", "HOLD")
        de = {"BUY": "🟢", "SELL": "🔴"}.get(dec, "🟡")

        L = []
        L.append(f"{de} <b>{e(sr.get('company_name', ticker))} ({e(ticker)})</b>")
        L.append(f"  <b>{e(dec)}</b> | Conf: {sr.get('ceo_confidence', 0):.0%} | Risk: {e(sr.get('risk_level', '-'))}")

        if sr.get("target_price"):
            L.append(f"  🎯 Target: ${sr['target_price']:.2f} | 🛑 Stop: ${sr.get('stop_loss', 0):.2f}")

        L.append(f"\n  💡 {e(sr.get('ceo_reasoning', '-')[:400])}")

        # Agent votes
        votes = sr.get("agent_votes", {})
        if votes:
            L.append(f"\n  <b>Agent Votes:</b>")
            for aname, v in votes.items():
                ve = {"BUY": "🟢", "SELL": "🔴"}.get(v.get("action", ""), "🟡")
                L.append(f"    {ve} {e(aname)}: {e(v.get('action', '-'))} "
                        f"({v.get('confidence', 0):.0%}, {e(v.get('risk', '-'))})")

        # Technicals
        L.append(f"\n  📊 RSI: {sr.get('rsi', 0):.0f} | MACD: {sr.get('macd', 0):.4f} | Beta: {e(sr.get('beta', '-'))}")
        L.append(f"  SMA50: ${sr.get('sma_50', 0):.2f} | SMA200: ${sr.get('sma_200', 0):.2f}")
        L.append(f"  P/E: {e(sr.get('pe_ratio', '-'))} | Analyst: {e(sr.get('analyst_rating', '-'))}")
        L.append(f"  52W: ${sr.get('52w_low', 0):.2f} — ${sr.get('52w_high', 0):.2f}")

        return "\n".join(L)

    def _fmt_review(self, prev: Dict) -> str:
        e = _esc
        L = []
        L.append(f"📊 <b>What Changed Since {e(prev.get('hour_label', 'Last Hour'))}</b>")
        L.append(f"  Accuracy: {prev.get('accuracy', 0):.0%} "
                f"({prev.get('correct_count', 0)}/{prev.get('total_count', 0)})\n")

        for r in prev.get("reviews", []):
            ic = "✅" if r["was_correct"] else "❌"
            L.append(f"  {ic} <b>{e(r['ticker'])}</b> {e(r['prev_action'])} "
                    f"${r['prev_price']:.2f}→${r['current_price']:.2f} ({r['change_pct']:+.2f}%)")
            if r.get("target_hit"):
                L.append(f"     🎯 Target hit!")
            if r.get("stop_hit"):
                L.append(f"     🛑 Stop hit!")

        L.append(f"\n  📝 {e(prev.get('learning_notes', '')[:200])}")
        return "\n".join(L)

    # ── Utilities ──

    def _split_message(self, text: str, max_len: int = 4096) -> list:
        if len(text) <= max_len:
            return [text]
        chunks = []
        for para in text.split("\n\n"):
            if not chunks or len(chunks[-1]) + len(para) + 2 > max_len:
                chunks.append(para)
            else:
                chunks[-1] += "\n\n" + para
        return [c.strip() for c in chunks if c.strip()]

    def _strip_html(self, text: str) -> str:
        text = re.sub(r'<b>(.*?)</b>', r'\1', text)
        text = re.sub(r'<i>(.*?)</i>', r'\1', text)
        text = re.sub(r'<[^>]+>', '', text)
        # Also unescape HTML entities for plain text
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        return text

    def test_connection(self) -> bool:
        """Test the Telegram bot connection and send a sample report."""
        if not self.enabled:
            print("❌ Telegram not configured.")
            return False

        result = self._api_call("getMe")
        if not result or not result.get("ok"):
            print("❌ Bot token invalid.")
            return False

        bot = result["result"]
        print(f"✅ Bot: @{bot.get('username')} ({bot.get('first_name')})")
        print(f"   Chat ID: {self.chat_id}")

        # Send test with realistic stock data containing special chars
        test_report = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M"),
            "cycle_number": "TEST",
            "market_regime": "BULL",
            "total_discovered": 156,
            "action_summary": {
                "total_buy": 2, "total_sell": 0, "total_hold": 3,
                "buy_recommendations": [
                    {"ticker": "AAPL", "price": 195.50, "confidence": 0.85,
                     "risk": "MEDIUM", "target": 210.0, "stop_loss": 188.0,
                     "reasoning": "RSI at 58 < 70 (not overbought). Revenue > 5%. MACD bullish & breaking SMA200."},
                    {"ticker": "JNJ", "price": 155.20, "confidence": 0.72,
                     "risk": "LOW", "target": 170.0, "stop_loss": 148.0,
                     "reasoning": "Johnson & Johnson showing strong dividend yield > 3%. P/E < sector average."},
                ],
                "sell_recommendations": [],
                "hold_recommendations": [
                    {"ticker": "MSFT"}, {"ticker": "GOOGL"}, {"ticker": "PG"},
                ],
            },
            "prev_hour_review": {
                "hour_label": "10:05",
                "accuracy": 0.80,
                "correct_count": 4,
                "total_count": 5,
                "learning_notes": "Good hour — agents reading market well. Procter & Gamble pick was correct.",
                "reviews": [
                    {"ticker": "AAPL", "prev_action": "BUY", "prev_price": 194.0,
                     "current_price": 195.50, "change_pct": 0.77, "was_correct": True,
                     "target_hit": False, "stop_hit": False},
                    {"ticker": "PG", "prev_action": "BUY", "prev_price": 162.0,
                     "current_price": 164.30, "change_pct": 1.42, "was_correct": True,
                     "target_hit": True, "stop_hit": False},
                ],
            },
            "multi_hour_review": {"trend": "improving"},
            "ranking_table": [
                {"rank": 1, "ticker": "AAPL", "price": 195.50, "daily_change": 1.25, "score": 95, "rsi": 58},
                {"rank": 2, "ticker": "NVDA", "price": 890.0, "daily_change": 2.30, "score": 91, "rsi": 62},
                {"rank": 3, "ticker": "JNJ", "price": 155.20, "daily_change": 0.80, "score": 88, "rsi": 55},
            ],
            "stock_reports": {
                "AAPL": {
                    "company_name": "Apple Inc.",
                    "ceo_decision": "BUY", "ceo_confidence": 0.85, "risk_level": "MEDIUM",
                    "target_price": 210.0, "stop_loss": 188.0,
                    "ceo_reasoning": "Strong momentum. RSI at 58 < 70, not overbought. "
                                    "Revenue growth > 5% YoY. MACD bullish crossover & SMA200 support.",
                    "agent_votes": {
                        "Market Analyst": {"action": "BUY", "confidence": 0.88, "risk": "MEDIUM"},
                        "News Analyst": {"action": "BUY", "confidence": 0.80, "risk": "LOW"},
                        "Quant Analyst": {"action": "HOLD", "confidence": 0.60, "risk": "MEDIUM"},
                        "Risk Manager": {"action": "BUY", "confidence": 0.82, "risk": "MEDIUM"},
                    },
                    "rsi": 58, "macd": 1.23, "beta": 1.15,
                    "sma_50": 190.0, "sma_200": 193.5,
                    "pe_ratio": 28.5, "analyst_rating": "buy",
                    "52w_low": 164.08, "52w_high": 199.62,
                },
            },
        }

        print(f"\n📤 Sending test report with special characters (& < >)...")
        ok = self.send_report(test_report)
        if ok:
            print(f"✅ Test report sent! Check your Telegram.")
            return True
        else:
            print(f"❌ Test report failed. Check logs above.")
            return False


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sender = TelegramSender()
    if sender.test_connection():
        print("\n🎉 Telegram is ready!")
    else:
        print("\n❌ Setup needed:")
        print("   1. Talk to @BotFather → /newbot")
        print("   2. Copy token")
        print("   3. Send /start to your bot")
        print("   4. Get chat ID from @userinfobot")
        print("   5. Add to .env:")
        print("      TELEGRAM_BOT_TOKEN=your-token")
        print("      TELEGRAM_CHAT_ID=your-chat-id")
