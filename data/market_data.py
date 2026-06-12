"""
Market Data Fetcher
===================
Fetches real-time and historical market data using yfinance.
Uses BATCH downloading to avoid Yahoo Finance rate limits.
Instead of 150 individual calls → a few batch calls.
"""

import time
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
import ta

logger = logging.getLogger(__name__)


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

    def _is_cache_valid(self, key: str, time_dict: dict, duration: timedelta) -> bool:
        return key in time_dict and datetime.now() - time_dict[key] < duration

    # ── Batch Download (the key fix) ──

    def _ensure_batch_data(self):
        """
        Download ALL tickers in a few batch requests.
        This replaces 150+ individual calls with ~3 batch calls.
        """
        if self._batch_time and datetime.now() - self._batch_time < self._batch_duration:
            if self._batch_data:
                return  # Cache still fresh

        logger.info(f"📦 Batch downloading data for {len(self.tickers)} tickers...")
        self._batch_data = {}

        # Split into chunks of 50 (Yahoo's practical limit per batch)
        chunk_size = 50
        chunks = [self.tickers[i:i + chunk_size] for i in range(0, len(self.tickers), chunk_size)]

        for ci, chunk in enumerate(chunks):
            try:
                time.sleep(1.5)  # Delay between batch requests
                ticker_str = " ".join(chunk)

                # Single API call for up to 50 tickers
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
                    logger.warning(f"  Batch {ci+1}/{len(chunks)}: empty response")
                    continue

                # If only 1 ticker, yfinance returns flat DataFrame
                if len(chunk) == 1:
                    ticker = chunk[0]
                    if not data.empty:
                        self._batch_data[ticker] = data
                        self._hist_cache[ticker] = data
                        self._hist_cache_time[ticker] = datetime.now()
                else:
                    # Multi-ticker: data has (ticker, field) columns
                    for ticker in chunk:
                        try:
                            if ticker in data.columns.get_level_values(0):
                                df = data[ticker].dropna(subset=["Close"])
                                if not df.empty:
                                    self._batch_data[ticker] = df
                                    self._hist_cache[ticker] = df
                                    self._hist_cache_time[ticker] = datetime.now()
                        except Exception:
                            pass

                logger.info(f"  Batch {ci+1}/{len(chunks)}: {len([t for t in chunk if t in self._batch_data])}/{len(chunk)} OK")

            except Exception as e:
                logger.error(f"  Batch {ci+1} download error: {e}")
                # If rate limited, wait longer
                if "Too Many" in str(e) or "Rate" in str(e) or "429" in str(e):
                    logger.warning(f"  ⚠️ Rate limited — waiting 15s before next batch...")
                    time.sleep(15)

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
        """Fetch company info with caching (2hr cache)."""
        if self._is_cache_valid(ticker, self._info_cache_time, timedelta(hours=2)):
            return self._info_cache.get(ticker, {"sector": "Unknown", "industry": "Unknown", "company_name": ticker})

        try:
            time.sleep(0.8)
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
            if "Too Many" in str(e) or "429" in str(e):
                logger.warning(f"⚠️ Rate limited on {ticker} info, backing off 10s...")
                time.sleep(10)
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
