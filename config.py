"""
AI Investment Bank — Hourly Report System Configuration
========================================================
This system generates HOURLY investment reports for YOU to act on.
It does NOT auto-trade. No broker credentials needed.

You only need:
  1. OPENAI_API_KEY  — for AI stock analysis
  2. TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID — to receive reports on your phone
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# LLM Configuration
# ============================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# ============================================================
# Stock Discovery Configuration
# ============================================================
# The system dynamically discovers stocks from the market.
# NO hardcoded list needed.

DISCOVERY_TOP_N = 50             # How many top-ranked stocks to keep after scoring
SCREENER_DEEP_ANALYZE_N = 5      # How many of the top 50 get deep analysis each cycle

# ============================================================
# Stock Screener Configuration
# ============================================================
SCREENER_RULES = {
    # Hard rules (must pass ALL)
    "min_market_cap": 5_000_000_000,      # $5B minimum
    "min_avg_volume": 2_000_000,          # 2M shares/day minimum
    "max_beta": 3.0,                      # Exclude extremely volatile
    "min_price": 5.0,                     # Exclude penny stocks

    # Soft scoring (points-based, contribute to score 0-100)
    "scoring": {
        "rsi_oversold_bonus": 15,
        "rsi_overbought_penalty": 15,
        "above_sma50_bonus": 10,
        "above_sma200_bonus": 15,
        "macd_bullish_bonus": 12,
        "volume_surge_bonus": 10,
        "near_52w_low_penalty": 10,
        "near_52w_high_bonus": 8,
        "analyst_buy_bonus": 10,
        "low_pe_bonus": 8,
        "earnings_growth_bonus": 10,
        "dividend_bonus": 5,
    },
    "min_score_to_pass": 30,              # Minimum score to be in top 50
    "max_stocks_per_cycle": 5,            # Max stocks to deep-analyze per cycle
}

# ============================================================
# AUTO-TRADING SCHEDULE
# ============================================================
# How the system runs automatically (HOURLY mode)

TRADING_SCHEDULE = {
    # Hourly report: runs every hour during market hours
    "report_mode": "hourly",               # "hourly" or "daily"

    # Market hours (Eastern Time)
    "market_open": "09:30",
    "market_close": "16:00",
    "timezone": "US/Eastern",

    # Hourly schedule: generates reports at these times
    "hourly_times": [
        "09:35",    # Just after market open
        "10:30",
        "11:30",
        "12:30",
        "13:30",
        "14:30",
        "15:30",
        "15:50",    # Near market close
    ],

    # Discovery refresh: re-scan every N hours
    "discovery_refresh_hours": 4,

    # Learning cycle: runs every hour after the report
    "learning_cycle_hours": 1,

    # Hourly tracker: how many hours of history to keep
    "tracker_history_hours": 48,

    # Review window for multi-hour trend analysis
    "multi_hour_review_window": 4,
}

# ============================================================
# Report-Only Mode (NO auto-trading)
# ============================================================
# This system generates reports only. You decide what to trade.
# No broker connection is needed.

# Trading configuration (used for analysis & risk assessment only,
# NOT for executing trades)
INITIAL_CAPITAL = 1_000_000.0
MAX_POSITION_SIZE_PCT = 0.10
MAX_PORTFOLIO_EXPOSURE_PCT = 0.80
STOP_LOSS_PCT = 0.05
TAKE_PROFIT_PCT = 0.15

# Keep this as fallback (used if discovery engine is offline)
FALLBACK_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "JPM", "V", "WMT",
    "JNJ", "UNH", "HD", "PG", "XOM",
]

# ============================================================
# Learning & Review Configuration
# ============================================================
REVIEW_INTERVAL_HOURS = 4
LEARNING_ALPHA = 0.1
MIN_DECISIONS_FOR_REVIEW = 5
CONFIDENCE_THRESHOLD = 0.65

# ============================================================
# News Configuration
# ============================================================
NEWS_FETCH_INTERVAL_MINUTES = 30
NEWS_LOOKBACK_DAYS = 3
NEWS_WEIGHT_IN_DECISION = 0.25

# ============================================================
# Agent Weight Configuration (learnable)
# ============================================================
DEFAULT_AGENT_WEIGHTS = {
    "market_analyst": 0.30,
    "news_analyst": 0.25,
    "quant_analyst": 0.25,
    "risk_manager": 0.20,
}

# ============================================================
# Risk Parameters (learnable)
# ============================================================
DEFAULT_RISK_PARAMS = {
    "max_volatility": 0.40,
    "max_beta": 2.0,
    "min_liquidity_avg_volume": 1_000_000,
    "max_sector_exposure": 0.30,
    "sentiment_threshold": -0.3,
}

# ============================================================
# Broker Connection (NOT NEEDED for report-only mode)
# ============================================================
# These are kept for reference if you ever want to add auto-trading.
# For the hourly report system, you do NOT need to configure any broker.
#
# BROKER_TYPE = os.getenv("BROKER_TYPE", "paper")
# ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
# ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
# IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
# IBKR_PORT = int(os.getenv("IBKR_PORT", "7497"))

# ============================================================
# Logging
# ============================================================
LOG_LEVEL = "INFO"
JOURNAL_DB_PATH = os.getenv("JOURNAL_DB_PATH", "decision_journal.db")
