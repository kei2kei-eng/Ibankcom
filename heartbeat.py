"""
Heartbeat & Status Monitor
===========================
Writes a live status file so you can ALWAYS see what the system is doing.
Also provides a `status` command and log viewer.
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

STATUS_FILE = "ibank_status.json"


def write_heartbeat(
    status: str,
    bank=None,
    details: str = "",
    step: str = "",
):
    """
    Write a heartbeat status file.
    This file is ALWAYS up-to-date — check it anytime.
    
    Args:
        status: "RUNNING", "IDLE", "TRADING", "MONITORING", "LEARNING", "STOPPED", "ERROR"
        bank: AIInvestmentBank instance
        details: Human-readable details
        step: Current step name
    """
    heartbeat = {
        "status": status,
        "step": step,
        "details": details,
        "timestamp": datetime.now().isoformat(),
        "uptime_info": "",
    }

    if bank:
        heartbeat.update({
            "broker": bank.broker.name,
            "portfolio_value": round(bank.portfolio.total_value, 2),
            "cash": round(bank.portfolio.cash, 2),
            "positions": bank.portfolio.num_positions,
            "pnl_pct": round(bank.portfolio.total_pnl_pct, 2),
            "trades_today": bank.trade_count_today,
            "discovered_stocks": len(bank.discovered_tickers),
            "top_50_count": len(bank.top_50),
            "last_discovery": bank._last_discovery_time.isoformat() if bank._last_discovery_time else None,
        })

    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(heartbeat, f, indent=2)
    except Exception:
        pass


def read_status() -> Dict:
    """Read the current status file."""
    if not os.path.exists(STATUS_FILE):
        return {"status": "NOT_STARTED", "message": "System has not been started yet."}
    try:
        with open(STATUS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {"status": "UNKNOWN", "message": "Could not read status file."}


def print_status_dashboard():
    """Print a beautiful status dashboard."""
    status = read_status()

    # Determine status emoji
    status_emoji = {
        "RUNNING": "🟢",
        "IDLE": "🟡",
        "TRADING": "🔴",
        "MONITORING": "🔵",
        "LEARNING": "🧠",
        "SCREENING": "🔬",
        "DISCOVERING": "🌍",
        "ANALYZING": "🔍",
        "STOPPED": "🔴",
        "ERROR": "❌",
        "NOT_STARTED": "⚪",
    }.get(status.get("status", ""), "⚪")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts = status.get("timestamp", "Unknown")
    age = ""
    if ts and ts != "Unknown":
        try:
            age_seconds = (datetime.now() - datetime.fromisoformat(ts)).total_seconds()
            if age_seconds < 60:
                age = f"{age_seconds:.0f}s ago"
            elif age_seconds < 3600:
                age = f"{age_seconds/60:.0f} min ago"
            else:
                age = f"{age_seconds/3600:.1f} hrs ago"
        except Exception:
            age = ""

    print(f"\n{'='*60}")
    print(f"🏦 AI INVESTMENT BANK — STATUS DASHBOARD")
    print(f"{'='*60}")
    print(f"  {status_emoji} Status: {status.get('status', 'UNKNOWN')}")
    if status.get("step"):
        print(f"  📋 Step: {status['step']}")
    if status.get("details"):
        print(f"  📝 {status['details']}")
    print(f"  🕐 Last heartbeat: {ts} ({age})")
    print(f"  🕐 Checked at: {now}")

    if status.get("broker"):
        print(f"\n  💰 Broker: {status['broker']}")
        print(f"  💵 Portfolio: ${status.get('portfolio_value', 0):,.2f}")
        print(f"  💵 Cash: ${status.get('cash', 0):,.2f}")
        print(f"  📊 Positions: {status.get('positions', 0)}")
        print(f"  📈 P&L: {status.get('pnl_pct', 0):+.2f}%")
        print(f"  📊 Trades today: {status.get('trades_today', 0)}")
        print(f"  🌍 Stocks discovered: {status.get('discovered_stocks', 0)}")

    # Check if stale (no heartbeat for 5+ minutes)
    if age:
        try:
            age_seconds = (datetime.now() - datetime.fromisoformat(ts)).total_seconds()
            if age_seconds > 300:
                print(f"\n  ⚠️  WARNING: No heartbeat for {age}!")
                print(f"     System may have crashed. Check ai_ibank.log")
        except Exception:
            pass

    print(f"{'='*60}\n")


def print_recent_log(lines: int = 30):
    """Print the last N lines of the log file."""
    log_file = "ai_ibank.log"
    if not os.path.exists(log_file):
        print("No log file found yet.")
        return

    print(f"\n📜 Recent Log (last {lines} lines):")
    print(f"{'='*60}")
    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            for line in all_lines[-lines:]:
                print(f"  {line.rstrip()}")
    except Exception as e:
        print(f"Error reading log: {e}")
    print(f"{'='*60}\n")
