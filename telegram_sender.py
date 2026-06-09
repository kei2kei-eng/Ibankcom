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
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Telegram Bot API base URL
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramSender:
    """
    Sends investment reports to Telegram.
    
    Features:
    - Sends formatted text summary as Telegram message
    - Sends HTML report as a document attachment
    - Supports message splitting for long reports
    - Emoji-rich formatting for readability on mobile
    """

    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.bot_token and self.chat_id)

        if self.enabled:
            # Verify bot works on init
            me = self._api_call("getMe")
            if me:
                bot_name = me.get("result", {}).get("username", "unknown")
                logger.info(f"📱 Telegram bot connected: @{bot_name} → Chat {self.chat_id}")
            else:
                logger.warning("📱 Telegram bot token invalid. Messages will fail.")
        else:
            logger.info("📱 Telegram not configured. Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env")

    def _api_call(self, method: str, data: dict = None, files: dict = None) -> Optional[Dict]:
        """Make a Telegram Bot API call."""
        if not self.bot_token:
            return None

        url = TELEGRAM_API_BASE.format(token=self.bot_token, method=method)

        try:
            if files:
                # File upload (multipart/form-data)
                import http.client
                import mimetypes
                boundary = "----PythonBoundary" + datetime.now().strftime("%Y%m%d%H%M%S%f")
                body = b""
                
                # Add regular fields
                if data:
                    for key, value in data.items():
                        body += f"--{boundary}\r\n".encode()
                        body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
                        body += f"{value}\r\n".encode()
                
                # Add file fields
                for field_name, file_info in files.items():
                    file_path, file_name, file_content = file_info
                    mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
                    body += f"--{boundary}\r\n".encode()
                    body += f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"\r\n'.encode()
                    body += f"Content-Type: {mime_type}\r\n\r\n".encode()
                    body += file_content
                    body += b"\r\n"
                
                body += f"--{boundary}--\r\n".encode()
                
                req = urllib.request.Request(url, data=body, method="POST")
                req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
                
            elif data:
                # JSON POST
                post_data = json.dumps(data).encode("utf-8")
                req = urllib.request.Request(url, data=post_data, method="POST")
                req.add_header("Content-Type", "application/json")
                
            else:
                # GET
                req = urllib.request.Request(url, method="GET")

            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("ok"):
                    return result
                else:
                    logger.error(f"Telegram API error: {result.get('description', 'unknown')}")
                    return result

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"Telegram HTTP error {e.code}: {error_body}")
            return None
        except Exception as e:
            logger.error(f"Telegram API call failed ({method}): {e}")
            return None

    def send_report(self, report: Dict) -> bool:
        """
        Send a complete hourly report via Telegram.
        
        Sends:
        1. A formatted summary message (with key decisions)
        2. The full HTML report as a document attachment
        """
        if not self.enabled:
            logger.info("📱 Telegram not configured. Report saved locally only.")
            return False

        success = True

        # 1. Send summary message
        summary_msg = self._format_summary_message(report)
        if not self._send_message(summary_msg):
            success = False

        # 2. Send detailed stock analysis (separate messages for each)
        for ticker, sr in report.get("stock_reports", {}).items():
            stock_msg = self._format_stock_message(ticker, sr)
            self._send_message(stock_msg)

        # 3. Send "What Changed" section if available
        prev = report.get("prev_hour_review", {})
        if prev.get("reviews"):
            review_msg = self._format_review_message(prev)
            self._send_message(review_msg)

        # 4. Send HTML report as document
        html_path = "report_latest.html"
        if os.path.exists(html_path):
            with open(html_path, "rb") as f:
                html_content = f.read()
            caption = (
                f"📄 Full HTML Report — {report['date']} {report['time']}\n"
                f"Open in browser for interactive view with charts & tables."
            )
            self._send_document(
                file_name=f"report_{report['date']}_{report['time'].replace(':', '')}.html",
                file_content=html_content,
                caption=caption,
            )

        if success:
            logger.info(f"📱 Report sent to Telegram chat {self.chat_id}")
        return success

    def _send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a text message. Splits into chunks if > 4096 chars."""
        if not self.enabled:
            return False

        # Telegram limit is 4096 chars per message
        chunks = self._split_message(text, max_len=4096)

        for i, chunk in enumerate(chunks):
            data = {
                "chat_id": self.chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            result = self._api_call("sendMessage", data=data)
            if not result or not result.get("ok"):
                # Try without parse_mode if HTML parsing fails
                if i == 0:
                    data.pop("parse_mode", None)
                    data["text"] = self._strip_html(chunk)
                    result = self._api_call("sendMessage", data=data)
                if not result or not result.get("ok"):
                    logger.error(f"Failed to send Telegram message chunk {i+1}/{len(chunks)}")
                    return False

        return True

    def _send_document(self, file_name: str, file_content: bytes, caption: str = "") -> bool:
        """Send a file as a Telegram document."""
        if not self.enabled:
            return False

        data = {
            "chat_id": self.chat_id,
            "caption": caption[:1024],  # Telegram caption limit
        }
        files = {
            "document": (file_name, file_name, file_content),
        }
        result = self._api_call("sendDocument", data=data, files=files)
        if result and result.get("ok"):
            logger.info(f"📱 Document sent: {file_name}")
            return True
        else:
            logger.error(f"Failed to send document: {file_name}")
            return False

    def _format_summary_message(self, report: Dict) -> str:
        """Format the main summary message for Telegram."""
        summary = report.get("action_summary", {})
        prev = report.get("prev_hour_review", {})
        multi = report.get("multi_hour_review", {})

        lines = []
        lines.append(f"🏦 <b>AI Investment Bank — Hourly Report #{report.get('cycle_number', '?')}</b>")
        lines.append(f"📅 {report['date']} {report['time']} | Regime: {report['market_regime']}")
        lines.append(f"📊 {report.get('total_discovered', 0)} stocks scanned")
        lines.append("")

        # Quick stats
        buy_emoji = "🟢" if summary.get("total_buy", 0) > 0 else "⚪"
        sell_emoji = "🔴" if summary.get("total_sell", 0) > 0 else "⚪"
        hold_emoji = "🟡"
        lines.append(f"{buy_emoji} BUY: <b>{summary.get('total_buy', 0)}</b>  |  "
                     f"{sell_emoji} SELL: <b>{summary.get('total_sell', 0)}</b>  |  "
                     f"{hold_emoji} HOLD: <b>{summary.get('total_hold', 0)}</b>")
        lines.append("")

        # Previous hour accuracy
        if prev.get("reviews"):
            acc = prev.get("accuracy", 0)
            acc_emoji = "📈" if acc > 0.6 else "📉" if acc < 0.4 else "➡️"
            lines.append(f"{acc_emoji} <b>Prev Hour Accuracy:</b> {acc:.0%} "
                        f"({prev.get('correct_count', 0)}/{prev.get('total_count', 0)})")
            lines.append(f"   {prev.get('learning_notes', '')[:100]}")
            lines.append("")

        # Multi-hour trend
        if multi.get("trend") and multi.get("trend") != "no_data":
            trend = multi["trend"].upper()
            trend_emoji = "📈" if trend == "IMPROVING" else "📉" if trend == "DECLINING" else "➡️"
            lines.append(f"{trend_emoji} <b>Trend:</b> {trend}")
            lines.append("")

        # BUY recommendations
        if summary.get("buy_recommendations"):
            lines.append("━" * 30)
            lines.append(f"🟢 <b>BUY RECOMMENDATIONS</b>")
            lines.append("━" * 30)
            for b in summary["buy_recommendations"]:
                lines.append(f"  <b>{b['ticker']}</b> @ ${b['price']:.2f}")
                lines.append(f"    Confidence: {b['confidence']:.0%} | Risk: {b['risk']}")
                if b.get("target"):
                    lines.append(f"    🎯 Target: ${b['target']:.2f} | 🛑 Stop: ${b.get('stop_loss', 'N/A')}")
                lines.append(f"    💡 {b['reasoning'][:200]}")
                lines.append("")

        # SELL recommendations
        if summary.get("sell_recommendations"):
            lines.append("━" * 30)
            lines.append(f"🔴 <b>SELL RECOMMENDATIONS</b>")
            lines.append("━" * 30)
            for s in summary["sell_recommendations"]:
                lines.append(f"  <b>{s['ticker']}</b> @ ${s['price']:.2f}")
                lines.append(f"    💡 {s['reasoning'][:200]}")
                lines.append("")

        # HOLD list
        if summary.get("hold_recommendations"):
            hold_str = ", ".join(f"<b>{h['ticker']}</b>" for h in summary["hold_recommendations"])
            lines.append(f"🟡 HOLD: {hold_str}")
            lines.append("")

        # Top 5 quick view
        ranking = report.get("ranking_table", [])[:5]
        if ranking:
            lines.append("━" * 30)
            lines.append("🏆 <b>TOP 5 STOCKS</b>")
            lines.append("━" * 30)
            for r in ranking:
                change_emoji = "🟢" if r["daily_change"] > 0 else "🔴"
                lines.append(f"  {r['rank']}. <b>{r['ticker']}</b> ${r['price']:.2f} "
                           f"{change_emoji} {r['daily_change']:+.2f}% "
                           f"Score:{r['score']:.0f} RSI:{r['rsi']:.0f}")

        lines.append("")
        lines.append("⏱ Next report in ~60 min")
        lines.append("⚠️ AI-generated analysis — Not financial advice")

        return "\n".join(lines)

    def _format_stock_message(self, ticker: str, sr: Dict) -> str:
        """Format a detailed stock analysis for Telegram."""
        decision = sr.get("ceo_decision", "HOLD")
        decision_emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(decision, "⚪")

        lines = []
        lines.append(f"{decision_emoji} <b>{sr.get('company_name', ticker)} ({ticker})</b>")
        lines.append(f"  Decision: <b>{decision}</b> | Confidence: {sr.get('ceo_confidence', 0):.0%} | Risk: {sr.get('risk_level', 'N/A')}")
        lines.append("")

        if sr.get("target_price"):
            lines.append(f"  🎯 Target: ${sr['target_price']:.2f} | 🛑 Stop: ${sr.get('stop_loss', 'N/A')}")
            lines.append("")

        # CEO reasoning
        lines.append(f"  💡 <b>Why:</b> {sr.get('ceo_reasoning', 'N/A')[:400]}")
        lines.append("")

        # Agent votes
        lines.append("  <b>Agent Votes:</b>")
        for agent_name, vote in sr.get("agent_votes", {}).items():
            vote_emoji = {"BUY": "🟢", "SELL": "🔴"}.get(vote["action"], "🟡")
            lines.append(f"    {vote_emoji} {agent_name}: {vote['action']} "
                        f"({vote['confidence']:.0%}, {vote['risk']})")
        lines.append("")

        # Technicals
        lines.append("  📊 <b>Technicals:</b>")
        lines.append(f"    RSI: {sr.get('rsi', 0):.0f} | MACD: {sr.get('macd', 0):.4f} | Beta: {sr.get('beta', 'N/A')}")
        lines.append(f"    SMA50: ${sr.get('sma_50', 0):.2f} | SMA200: ${sr.get('sma_200', 0):.2f}")
        lines.append(f"    P/E: {sr.get('pe_ratio', 'N/A')} | Analyst: {sr.get('analyst_rating', 'N/A')}")
        lines.append(f"    52W: ${sr.get('52w_low', 0):.2f} — ${sr.get('52w_high', 0):.2f}")

        return "\n".join(lines)

    def _format_review_message(self, prev: Dict) -> str:
        """Format the "What Changed" review for Telegram."""
        lines = []
        lines.append(f"📊 <b>What Changed Since {prev.get('hour_label', 'Last Hour')}</b>")
        lines.append(f"  Accuracy: {prev.get('accuracy', 0):.0%} "
                    f"({prev.get('correct_count', 0)}/{prev.get('total_count', 0)})")
        lines.append("")

        for r in prev.get("reviews", []):
            icon = "✅" if r["was_correct"] else "❌"
            lines.append(f"  {icon} <b>{r['ticker']}</b> {r['prev_action']} "
                        f"${r['prev_price']:.2f}→${r['current_price']:.2f} ({r['change_pct']:+.2f}%)")
            if r.get("target_hit"):
                lines.append(f"     🎯 Target hit!")
            if r.get("stop_hit"):
                lines.append(f"     🛑 Stop loss hit!")

        lines.append(f"\n  📝 {prev.get('learning_notes', '')[:200]}")

        return "\n".join(lines)

    def _split_message(self, text: str, max_len: int = 4096) -> list:
        """Split a long message into chunks that fit Telegram limits."""
        if len(text) <= max_len:
            return [text]

        chunks = []
        # Try to split at double newlines (paragraph breaks)
        paragraphs = text.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 > max_len:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                # If single paragraph is too long, split at newlines
                if len(para) > max_len:
                    for line in para.split("\n"):
                        if len(current_chunk) + len(line) + 1 > max_len:
                            chunks.append(current_chunk.strip())
                            current_chunk = line + "\n"
                        else:
                            current_chunk += line + "\n"
                else:
                    current_chunk = para + "\n\n"
            else:
                current_chunk += para + "\n\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks

    def _strip_html(self, text: str) -> str:
        """Strip HTML tags for fallback plain-text sending."""
        import re
        text = re.sub(r'<b>(.*?)</b>', r'\1', text)
        text = re.sub(r'<i>(.*?)</i>', r'\1', text)
        text = re.sub(r'<code>(.*?)</code>', r'\1', text)
        text = re.sub(r'<[^>]+>', '', text)
        return text

    def test_connection(self) -> bool:
        """Test the Telegram bot connection."""
        if not self.enabled:
            print("❌ Telegram not configured.")
            print("   Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
            return False

        result = self._api_call("getMe")
        if result and result.get("ok"):
            bot_info = result.get("result", {})
            print(f"✅ Bot connected: @{bot_info.get('username', 'unknown')}")
            print(f"   Bot name: {bot_info.get('first_name', 'unknown')}")
            print(f"   Chat ID: {self.chat_id}")

            # Send test message
            test_result = self._send_message(
                "🦞 <b>小龍蝦 AI Investment Bank</b>\n\n"
                "✅ Telegram connection successful!\n"
                "You will receive hourly stock reports here."
            )
            if test_result:
                print("✅ Test message sent!")
                return True
            else:
                print("❌ Test message failed. Check CHAT_ID.")
                return False
        else:
            print("❌ Bot token invalid. Check TELEGRAM_BOT_TOKEN.")
            return False


# ── CLI test ──
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    sender = TelegramSender()
    if sender.test_connection():
        print("\n🎉 Telegram is ready to receive hourly reports!")
    else:
        print("\n❌ Setup needed:")
        print("   1. Talk to @BotFather on Telegram → /newbot")
        print("   2. Copy the token")
        print("   3. Send /start to your bot")
        print("   4. Get your chat ID (talk to @userinfobot)")
        print("   5. Add to .env:")
        print("      TELEGRAM_BOT_TOKEN=your-token-here")
        print("      TELEGRAM_CHAT_ID=your-chat-id-here")
