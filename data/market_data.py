"""
Market Data Fetcher
===================
Fetches real-time and historical market data using yfinance.
Includes rate limiting to avoid Yahoo Finance 429 errors.
"""

import time
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
import ta

logger = logging.getLogger(__name__)

# ── Global rate limiter ──
_last_request_time = 0.0
_MIN_INTERVAL = 0.8  # seconds between yfinance calls (Yahoo limit ~5/min sustained)


def _rate_limit_wait():
    """Wait if we're hitting Yahoo Finance too fast."""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _MIN_INTERVAL:
        wait = _MIN_INTERVAL - elapsed
        time.sleep(wait)
    _last_request_time = time.time()


class MarketDataFetcher:
    """Fetches and processes market data for the trading system."""

    def __init__(self, tickers: List[str]):
        self.tickers = tickers
        self._cache: Dict[str, pd.DataFrame] = {}
        self._info_cache: Dict[str, Dict] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._info_cache_time: Dict[str, datetime] = {}
        self.cache_duration = timedelta(minutes=30)
        self.info_cache_duration = timedelta(hours=2)
        self._rate_limit_errors = 0
        self._max_consecutive_errors = 5

    def _is_cache_valid(self, cache_key: str, cache_time_dict: dict, duration: timedelta) -> bool:
        if cache_key not in cache_time_dict:
            return False
        return datetime.now() - cache_time_dict[cache_key] < duration

    def get_stock_data(self, ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
        """Fetch stock data with caching and rate limiting."""
        cache_key = f"{ticker}_{period}_{interval}"
        if self._is_cache_valid(cache_key, self._cache_time, self.cache_duration):
            return self._cache.get(cache_key, pd.DataFrame())

        try:
            _rate_limit_wait()
            stock = yf.Ticker(ticker)
            df = stock.history(period=period, interval=interval)
            if df.empty:
                logger.warning(f"No data returned for {ticker}")
                return pd.DataFrame()

            self._cache[cache_key] = df
            self._cache_time[cache_key] = datetime.now()
            self._rate_limit_errors = 0  # reset on success
            return df

        except Exception as e:
            err_msg = str(e)
            if "Too Many" in err_msg or "Rate" in err_msg or "429" in err_msg:
                self._rate_limit_errors += 1
                logger.warning(f"⚠️ Rate limited on {ticker} (error #{self._rate_limit_errors}). "
                             f"Backing off...")
                # Exponential backoff: 3s, 6s, 12s...
                backoff = min(3 * (2 ** self._rate_limit_errors), 30)
                time.sleep(backoff)
            else:
                logger.error(f"Error fetching data for {ticker}: {e}")
            return pd.DataFrame()

    def get_technical_indicators(self, ticker: str) -> Dict:
        """Calculate comprehensive technical indicators."""
        df = self.get_stock_data(ticker, period="6mo")
        if df.empty:
            return {}

        try:
            indicators = {}

            # Trend Indicators
            indicators["sma_20"] = ta.trend.sma_indicator(df["Close"], window=20).iloc[-1]
            indicators["sma_50"] = ta.trend.sma_indicator(df["Close"], window=50).iloc[-1]
            indicators["sma_200"] = ta.trend.sma_indicator(df["Close"], window=200).iloc[-1]
            indicators["ema_12"] = ta.trend.ema_indicator(df["Close"], window=12).iloc[-1]
            indicators["ema_26"] = ta.trend.ema_indicator(df["Close"], window=26).iloc[-1]

            # MACD
            macd = ta.trend.MACD(df["Close"])
            indicators["macd"] = macd.macd().iloc[-1]
            indicators["macd_signal"] = macd.macd_signal().iloc[-1]
            indicators["macd_histogram"] = macd.macd_diff().iloc[-1]

            # RSI
            indicators["rsi"] = ta.momentum.rsi(df["Close"], window=14).iloc[-1]

            # Bollinger Bands
            bb = ta.volatility.BollingerBands(df["Close"])
            indicators["bb_upper"] = bb.bollinger_hband().iloc[-1]
            indicators["bb_lower"] = bb.bollinger_lband().iloc[-1]
            indicators["bb_mid"] = bb.bollinger_mavg().iloc[-1]

            # ATR (volatility)
            indicators["atr"] = ta.volatility.average_true_range(
                df["High"], df["Low"], df["Close"], window=14
            ).iloc[-1]

            # Stochastic Oscillator
            indicators["stoch_k"] = ta.momentum.stoch(
                df["High"], df["Low"], df["Close"]
            ).iloc[-1]
            indicators["stoch_d"] = ta.momentum.stoch_signal(
                df["High"], df["Low"], df["Close"]
            ).iloc[-1]

            # Volume indicators
            indicators["obv"] = ta.volume.on_balance_volume(
                df["Close"], df["Volume"]
            ).iloc[-1]
            indicators["volume_sma"] = df["Volume"].rolling(20).mean().iloc[-1]
            indicators["current_volume"] = df["Volume"].iloc[-1]

            # Current price info
            indicators["current_price"] = df["Close"].iloc[-1]
            indicators["prev_close"] = df["Close"].iloc[-2] if len(df) > 1 else df["Close"].iloc[-1]
            indicators["daily_change_pct"] = (
                (df["Close"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2] * 100
                if len(df) > 1 else 0
            )

            # Calculate volatility (30-day)
            returns = df["Close"].pct_change().dropna()
            indicators["volatility_30d"] = returns.tail(30).std() * np.sqrt(252)

            # Support and Resistance levels
            indicators["support"] = df["Low"].tail(30).min()
            indicators["resistance"] = df["High"].tail(30).max()

            return indicators
        except Exception as e:
            logger.error(f"Error calculating indicators for {ticker}: {e}")
            return {"current_price": df["Close"].iloc[-1] if not df.empty else 0}

    def get_company_info(self, ticker: str) -> Dict:
        """Fetch company fundamental information with caching."""
        if self._is_cache_valid(ticker, self._info_cache_time, self.info_cache_duration):
            return self._info_cache.get(ticker, {"sector": "Unknown", "industry": "Unknown"})

        try:
            _rate_limit_wait()
            stock = yf.Ticker(ticker)
            info = stock.info
            result = {
                "sector": info.get("sector", "Unknown"),
                "industry": info.get("industry", "Unknown"),
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE", None),
                "forward_pe": info.get("forwardPE", None),
                "peg_ratio": info.get("pegRatio", None),
                "dividend_yield": info.get("dividendYield", 0),
                "beta": info.get("beta", 1.0),
                "eps": info.get("trailingEps", None),
                "revenue_growth": info.get("revenueGrowth", None),
                "profit_margin": info.get("profitMargins", None),
                "52w_high": info.get("fiftyTwoWeekHigh", None),
                "52w_low": info.get("fiftyTwoWeekLow", None),
                "avg_volume": info.get("averageVolume", 0),
                "short_ratio": info.get("shortRatio", None),
                "analyst_rating": info.get("recommendationKey", "Unknown"),
                "target_price": info.get("targetMeanPrice", None),
                "company_name": info.get("longName", ticker),
            }
            self._info_cache[ticker] = result
            self._info_cache_time[ticker] = datetime.now()
            self._rate_limit_errors = 0
            return result
        except Exception as e:
            err_msg = str(e)
            if "Too Many" in err_msg or "Rate" in err_msg or "429" in err_msg:
                self._rate_limit_errors += 1
                backoff = min(3 * (2 ** self._rate_limit_errors), 30)
                logger.warning(f"⚠️ Rate limited on {ticker} info. Backing off {backoff}s...")
                time.sleep(backoff)
            else:
                logger.error(f"Error fetching company info for {ticker}: {e}")
            return {"sector": "Unknown", "industry": "Unknown", "company_name": ticker}

    def get_all_tickers_snapshot(self) -> Dict[str, Dict]:
        """Get technical indicators for all tracked tickers (with rate limiting)."""
        results = {}
        total = len(self.tickers)
        for i, ticker in enumerate(self.tickers):
            if i > 0 and i % 10 == 0:
                logger.info(f"  Progress: {i}/{total} tickers fetched...")
            indicators = self.get_technical_indicators(ticker)
            info = self.get_company_info(ticker)
            if indicators:
                results[ticker] = {**indicators, **info}
        return results

    def generate_market_summary(self, ticker: str) -> str:
        """Generate a human-readable market summary for LLM consumption."""
        indicators = self.get_technical_indicators(ticker)
        info = self.get_company_info(ticker)

        if not indicators:
            return f"No market data available for {ticker}"

        return f"""
=== Market Data Summary for {info.get('company_name', ticker)} ({ticker}) ===

Current Price: ${indicators.get('current_price', 0):.2f}
Daily Change: {indicators.get('daily_change_pct', 0):.2f}%
Sector: {info.get('sector', 'Unknown')}
Market Cap: ${info.get('market_cap', 0):,.0f}
P/E Ratio: {info.get('pe_ratio', 'N/A')}
Beta: {info.get('beta', 'N/A')}

--- Technical Indicators ---
RSI (14): {indicators.get('rsi', 0):.1f}
MACD: {indicators.get('macd', 0):.4f} (Signal: {indicators.get('macd_signal', 0):.4f})
SMA 20: ${indicators.get('sma_20', 0):.2f}
SMA 50: ${indicators.get('sma_50', 0):.2f}
SMA 200: ${indicators.get('sma_200', 0):.2f}
Bollinger Band Upper: ${indicators.get('bb_upper', 0):.2f}
Bollinger Band Lower: ${indicators.get('bb_lower', 0):.2f}
ATR (Volatility): {indicators.get('atr', 0):.4f}
30-Day Volatility: {indicators.get('volatility_30d', 0):.4f}
Stochastic %K: {indicators.get('stoch_k', 0):.1f}

--- Support/Resistance ---
Support: ${indicators.get('support', 0):.2f}
Resistance: ${indicators.get('resistance', 0):.2f}
52-Week High: ${info.get('52w_high', 0):.2f}
52-Week Low: ${info.get('52w_low', 0):.2f}
Analyst Target: ${info.get('target_price', 'N/A')}
Analyst Rating: {info.get('analyst_rating', 'N/A')}

--- Volume ---
Current Volume: {indicators.get('current_volume', 0):,.0f}
20-Day Avg Volume: {indicators.get('volume_sma', 0):,.0f}
"""
