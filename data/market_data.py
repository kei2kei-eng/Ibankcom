"""
Market Data Fetcher
===================
Fetches real-time and historical market data using yfinance.
Uses BATCH downloading to avoid Yahoo Finance rate limits.
Instead of 150 individual calls → a few batch calls.
"""

import time
import warnings
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
import ta

logger = logging.getLogger(__name__)

# Suppress yfinance's noisy "possibly delisted" and "No data found" warnings
warnings.filterwarnings("ignore", message=".*possibly delisted.*")
warnings.filterwarnings("ignore", message=".*No data found.*")
# Also suppress the specific yfinance logger noise
yf_logger = logging.getLogger("yfinance")
yf_logger.setLevel(logging.ERROR)


class MarketDataFetcher:
    """
    Fetches and processes market data.
    Uses batch downloads to minimize API calls to Yahoo Finance.
    """

    def __init__(self, tickers: List[str]):
        self.tickers = tickers
        # Per-ticker caches
        self._hist_cache: Dict[str, pd.DataFrame] = {}
        self._hist_cache_time: Dict[str, datetime] = {}
        self._info_cache: Dict[str, Dict] = {}
        self._info_cache_time: Dict[str, datetime] = {}
        # Batch cache
        self._batch_data: Dict[str, pd.DataFrame] = {}
        self._batch_time: Optional[datetime] = None
        self._batch_duration = timedelta(minutes=30)
        # Info cache: 4 hours (was 2hr — longer cache = fewer API calls)
        self._info_cache_duration = timedelta(hours=4)
        # Rate limit guard for company info calls
        self._last_info_call_time: float = 0
        self._info_call_interval: float = 1.2  # seconds between info calls (was 0.8)

    def _is_cache_valid(self, key: str, time_dict: dict, duration: timedelta) -> bool:
        return key in time_dict and datetime.now() - time_dict[key] < duration

    # ── Batch Download (the key fix) ──

    def _download_one_batch(self, ticker_str: str, chunk: List[str], ci: int, total_chunks: int,
                            max_retries: int = 3) -> int:
        """
        Download one batch of tickers with retry logic.
        Returns: number of tickers successfully fetched from this batch.
        """
        for attempt in range(1, max_retries + 1):
            try:
                data = yf.download(
                    ticker_str,
                    period="6mo",
                    interval="1d",
                    group_by="ticker",
                    threads=False,
                    progress=False,
                    auto_adjust=True,
                )

                if data.empty:
                    # Could be rate limited with no data returned
                    ok_count = 0
                else:
                    # Parse results
                    if len(chunk) == 1:
                        ticker = chunk[0]
                        if not data.empty:
                            self._batch_data[ticker] = data
                            self._hist_cache[ticker] = data
                            self._hist_cache_time[ticker] = datetime.now()
                            ok_count = 1
                        else:
                            ok_count = 0
                    else:
                        ok_count = 0
                        for ticker in chunk:
                            try:
                                if ticker in data.columns.get_level_values(0):
                                    df = data[ticker].dropna(subset=["Close"])
                                    if not df.empty:
                                        self._batch_data[ticker] = df
                                        self._hist_cache[ticker] = df
                                        self._hist_cache_time[ticker] = datetime.now()
                                        ok_count += 1
                            except Exception:
                                pass

                # Check if most tickers failed → likely rate limited
                failed_count = len(chunk) - ok_count
                if failed_count > len(chunk) * 0.8 and attempt < max_retries:
                    logger.warning(f"  Batch {ci+1}/{total_chunks} attempt {attempt}: "
                                   f"only {ok_count}/{len(chunk)} OK — likely rate limited, "
                                   f"waiting {30 * attempt}s before retry...")
                    time.sleep(30 * attempt)  # Exponential backoff: 30s, 60s, 90s
                    continue

                return ok_count

            except Exception as e:
                err_str = str(e)
                if "Too Many" in err_str or "Rate" in err_str or "429" in err_str:
                    if attempt < max_retries:
                        wait = 30 * attempt
                        logger.warning(f"  Batch {ci+1}/{total_chunks} attempt {attempt}: "
                                       f"rate limited — waiting {wait}s before retry...")
                        time.sleep(wait)
                        continue
                    else:
                        logger.error(f"  Batch {ci+1}/{total_chunks}: FAILED after {max_retries} retries")
                        return 0
                else:
                    logger.error(f"  Batch {ci+1}/{total_chunks} error: {e}")
                    return 0

        return 0

    def _ensure_batch_data(self):
        """
        Download ALL tickers in small batch requests with retry logic.
        Uses chunks of 20 tickers (not 50) with 5s gaps and 3 retries per chunk.
        """
        if self._batch_time and datetime.now() - self._batch_time < self._batch_duration:
            if self._batch_data:
                return  # Cache still fresh

        logger.info(f"📦 Batch downloading data for {len(self.tickers)} tickers...")
        self._batch_data = {}

        # Small chunks to avoid triggering Yahoo's rate limit
        chunk_size = 20
        chunks = [self.tickers[i:i + chunk_size] for i in range(0, len(self.tickers), chunk_size)]

        # Initial delay — let any previous yfinance calls settle
        time.sleep(3)

        total_ok = 0
        for ci, chunk in enumerate(chunks):
            ticker_str = " ".join(chunk)
            ok_count = self._download_one_batch(ticker_str, chunk, ci, len(chunks))
            total_ok += ok_count

            logger.info(f"  Batch {ci+1}/{len(chunks)}: {ok_count}/{len(chunk)} OK "
                        f"(total: {total_ok}/{len(self.tickers)})")

            # Delay between batches (5s) — longer if we had failures
            if ci < len(chunks) - 1:
                if ok_count < len(chunk) * 0.5:
                    logger.info(f"  ⏳ Many failures in this batch — waiting 10s before next...")
                    time.sleep(10)
                else:
                    time.sleep(5)

        self._batch_time = datetime.now()
        logger.info(f"📦 Batch complete: {len(self._batch_data)}/{len(self.tickers)} tickers have data")

    def get_stock_data(self, ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
        """Fetch stock data. Uses batch cache if available."""
        cache_key = f"{ticker}_{period}_{interval}"

        # Check per-ticker cache first
        if self._is_cache_valid(cache_key, self._hist_cache_time, self._batch_duration):
            return self._hist_cache.get(cache_key, pd.DataFrame())

        # Check batch cache
        if ticker in self._batch_data:
            return self._batch_data[ticker]

        # Fallback: single request with delay
        try:
            time.sleep(1.0)
            stock = yf.Ticker(ticker)
            df = stock.history(period=period, interval=interval)
            if df.empty:
                logger.warning(f"No data returned for {ticker}")
                return pd.DataFrame()
            self._hist_cache[cache_key] = df
            self._hist_cache_time[cache_key] = datetime.now()
            return df
        except Exception as e:
            if "Too Many" in str(e) or "429" in str(e):
                logger.warning(f"⚠️ Rate limited on {ticker}, backing off 10s...")
                time.sleep(10)
            else:
                logger.error(f"Error fetching data for {ticker}: {e}")
            return pd.DataFrame()

    def get_technical_indicators(self, ticker: str) -> Dict:
        """Calculate comprehensive technical indicators."""
        df = self.get_stock_data(ticker, period="6mo")
        if df.empty:
            return {}

        try:
            close = df["Close"]
            high = df["High"]
            low = df["Low"]
            volume = df["Volume"]

            indicators = {}

            # Trend Indicators
            indicators["sma_20"] = ta.trend.sma_indicator(close, window=20).iloc[-1]
            indicators["sma_50"] = ta.trend.sma_indicator(close, window=50).iloc[-1]
            indicators["sma_200"] = ta.trend.sma_indicator(close, window=200).iloc[-1]
            indicators["ema_12"] = ta.trend.ema_indicator(close, window=12).iloc[-1]
            indicators["ema_26"] = ta.trend.ema_indicator(close, window=26).iloc[-1]

            # MACD
            macd = ta.trend.MACD(close)
            indicators["macd"] = macd.macd().iloc[-1]
            indicators["macd_signal"] = macd.macd_signal().iloc[-1]
            indicators["macd_histogram"] = macd.macd_diff().iloc[-1]

            # RSI
            indicators["rsi"] = ta.momentum.rsi(close, window=14).iloc[-1]

            # Bollinger Bands
            bb = ta.volatility.BollingerBands(close)
            indicators["bb_upper"] = bb.bollinger_hband().iloc[-1]
            indicators["bb_lower"] = bb.bollinger_lband().iloc[-1]
            indicators["bb_mid"] = bb.bollinger_mavg().iloc[-1]

            # ATR (volatility)
            indicators["atr"] = ta.volatility.average_true_range(high, low, close, window=14).iloc[-1]

            # Stochastic
            indicators["stoch_k"] = ta.momentum.stoch(high, low, close).iloc[-1]
            indicators["stoch_d"] = ta.momentum.stoch_signal(high, low, close).iloc[-1]

            # Volume
            indicators["obv"] = ta.volume.on_balance_volume(close, volume).iloc[-1]
            indicators["volume_sma"] = volume.rolling(20).mean().iloc[-1]
            indicators["current_volume"] = volume.iloc[-1]

            # Current price info
            indicators["current_price"] = float(close.iloc[-1])
            indicators["prev_close"] = float(close.iloc[-2]) if len(close) > 1 else float(close.iloc[-1])
            indicators["daily_change_pct"] = (
                (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
                if len(close) > 1 else 0
            )

            # Volatility (30-day)
            returns = close.pct_change().dropna()
            indicators["volatility_30d"] = returns.tail(30).std() * np.sqrt(252)

            # Support / Resistance
            indicators["support"] = float(low.tail(30).min())
            indicators["resistance"] = float(high.tail(30).max())

            return indicators

        except Exception as e:
            logger.error(f"Error calculating indicators for {ticker}: {e}")
            return {"current_price": float(df["Close"].iloc[-1]) if not df.empty else 0}

    def get_company_info(self, ticker: str) -> Dict:
        """Fetch company info with 4hr caching and rate-limit-safe throttling."""
        # Check cache first (4 hour cache)
        if self._is_cache_valid(ticker, self._info_cache_time, self._info_cache_duration):
            return self._info_cache.get(ticker, {"sector": "Unknown", "industry": "Unknown", "company_name": ticker})

        # Throttle: ensure minimum gap between info API calls
        elapsed_since_last = time.time() - self._last_info_call_time
        if elapsed_since_last < self._info_call_interval:
            time.sleep(self._info_call_interval - elapsed_since_last)

        try:
            self._last_info_call_time = time.time()
            stock = yf.Ticker(ticker)
            info = stock.info or {}
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
            return result
        except Exception as e:
            if "Too Many" in str(e) or "429" in str(e) or "Rate" in str(e):
                logger.warning(f"⚠️ Rate limited on {ticker} info, backing off 15s...")
                time.sleep(15)
            else:
                logger.debug(f"Info error for {ticker}: {e}")
            return {"sector": "Unknown", "industry": "Unknown", "company_name": ticker}

    def get_all_tickers_snapshot(self) -> Dict[str, Dict]:
        """Get all tickers via batch download, then company info individually."""
        self._ensure_batch_data()
        results = {}
        for ticker in self.tickers:
            indicators = self.get_technical_indicators(ticker)
            info = self.get_company_info(ticker)
            if indicators:
                results[ticker] = {**indicators, **info}
        return results

    def get_company_info_batch(self, tickers: List[str]) -> Dict[str, Dict]:
        """
        Fetch company info for a list of tickers with proper throttling.
        Returns dict: {ticker: company_info_dict}
        """
        results = {}
        for i, ticker in enumerate(tickers):
            results[ticker] = self.get_company_info(ticker)
            if (i + 1) % 10 == 0:
                logger.info(f"  📋 Company info: {i+1}/{len(tickers)} fetched")
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
