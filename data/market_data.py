"""
Market Data Fetcher
===================
Fetches real-time and historical market data using yfinance.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
import ta
import time

logger = logging.getLogger(__name__)

# Rate limiting: Add delay between API calls to avoid hitting yfinance limits
API_CALL_DELAY = 0.5  # 500ms delay between requests


class MarketDataFetcher:
    """Fetches and processes market data for the trading system."""

    def __init__(self, tickers: List[str]):
        self.tickers = tickers
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_time: Dict[str, datetime] = {}
        self.cache_duration = timedelta(minutes=15)
        self._last_api_call = 0  # Track last API call time

    def _is_cache_valid(self, ticker: str) -> bool:
        if ticker not in self._cache:
            return False
        if ticker not in self._cache_time:
            return False
        return datetime.now() - self._cache_time[ticker] < self.cache_duration

    def _apply_rate_limit(self):
        """Apply rate limiting delay between API calls."""
        elapsed = time.time() - self._last_api_call
        if elapsed < API_CALL_DELAY:
            time.sleep(API_CALL_DELAY - elapsed)
        self._last_api_call = time.time()

    def get_stock_data(self, ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
        """Fetch stock data with caching and rate limiting."""
        cache_key = f"{ticker}_{period}_{interval}"
        if self._is_cache_valid(cache_key):
            logger.debug(f"Cache hit for {ticker}")
            return self._cache[cache_key]

        try:
            # Apply rate limiting before API call
            self._apply_rate_limit()
            logger.debug(f"Fetching data for {ticker} (rate limited)")
            
            stock = yf.Ticker(ticker)
            df = stock.history(period=period, interval=interval)
            if df.empty:
                logger.warning(f"No data returned for {ticker}")
                return pd.DataFrame()

            self._cache[cache_key] = df
            self._cache_time[cache_key] = datetime.now()
            return df
        except Exception as e:
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
            indicators["ema_12"] = ta.trend.ema_indicator(df["Close"], window=12).iloc[-1]
            indicators["ema_26"] = ta.trend.ema_indicator(df["Close"], window=26).iloc[-1]

            # Momentum Indicators
            indicators["rsi"] = ta.momentum.rsi(df["Close"], window=14).iloc[-1]
            indicators["macd"] = ta.trend.macd_diff(df["Close"]).iloc[-1]
            indicators["stoch_k"] = ta.momentum.stoch(df["High"], df["Low"], df["Close"]).iloc[-1]

            # Volatility Indicators
            indicators["bb_high"] = ta.volatility.bollinger_hband(df["Close"]).iloc[-1]
            indicators["bb_low"] = ta.volatility.bollinger_lband(df["Close"]).iloc[-1]
            indicators["atr"] = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"]).iloc[-1]

            # Volume Indicators
            indicators["obv"] = ta.volume.on_balance_volume(df["Close"], df["Volume"]).iloc[-1]

            return indicators
        except Exception as e:
            logger.error(f"Error calculating indicators for {ticker}: {e}")
            return {}

    def get_batch_data(self, tickers: List[str]) -> Dict[str, pd.DataFrame]:
        """Fetch data for multiple tickers with rate limiting."""
        results = {}
        for ticker in tickers:
            try:
                results[ticker] = self.get_stock_data(ticker)
            except Exception as e:
                logger.error(f"Error fetching batch data for {ticker}: {e}")
                results[ticker] = pd.DataFrame()
        return results

    def get_current_price(self, ticker: str) -> Optional[float]:
        """Get current price for a ticker."""
        df = self.get_stock_data(ticker, period="1d")
        if df.empty:
            return None
        return df["Close"].iloc[-1]

    def get_price_change(self, ticker: str, days: int = 1) -> Optional[float]:
        """Get price change percentage over N days."""
        df = self.get_stock_data(ticker, period="6mo")
        if df.empty or len(df) < days + 1:
            return None
        old_price = df["Close"].iloc[-days - 1]
        new_price = df["Close"].iloc[-1]
        return ((new_price - old_price) / old_price) * 100

    def get_volatility(self, ticker: str, window: int = 20) -> Optional[float]:
        """Calculate rolling volatility."""
        df = self.get_stock_data(ticker, period="6mo")
        if df.empty or len(df) < window:
            return None
        returns = df["Close"].pct_change()
        return returns.rolling(window=window).std().iloc[-1]

    def get_support_resistance(self, ticker: str, period: int = 20) -> Dict[str, float]:
        """Calculate support and resistance levels."""
        df = self.get_stock_data(ticker, period="6mo")
        if df.empty or len(df) < period:
            return {}

        try:
            recent = df.tail(period)
            support = recent["Low"].min()
            resistance = recent["High"].max()
            current = df["Close"].iloc[-1]
            
            return {
                "support": support,
                "resistance": resistance,
                "current": current,
                "distance_to_support": ((current - support) / current) * 100,
                "distance_to_resistance": ((resistance - current) / current) * 100
            }
        except Exception as e:
            logger.error(f"Error calculating support/resistance for {ticker}: {e}")
            return {}

    def get_moving_averages(self, ticker: str) -> Dict[str, float]:
        """Get multiple moving averages."""
        df = self.get_stock_data(ticker, period="6mo")
        if df.empty:
            return {}

        try:
            return {
                "sma_10": ta.trend.sma_indicator(df["Close"], window=10).iloc[-1],
                "sma_20": ta.trend.sma_indicator(df["Close"], window=20).iloc[-1],
                "sma_50": ta.trend.sma_indicator(df["Close"], window=50).iloc[-1],
                "sma_200": ta.trend.sma_indicator(df["Close"], window=200).iloc[-1] if len(df) >= 200 else None,
                "ema_12": ta.trend.ema_indicator(df["Close"], window=12).iloc[-1],
                "ema_26": ta.trend.ema_indicator(df["Close"], window=26).iloc[-1],
            }
        except Exception as e:
            logger.error(f"Error calculating moving averages for {ticker}: {e}")
            return {}

    def get_rsi(self, ticker: str, period: int = 14) -> Optional[float]:
        """Get RSI indicator."""
        df = self.get_stock_data(ticker, period="6mo")
        if df.empty or len(df) < period:
            return None

        try:
            return ta.momentum.rsi(df["Close"], window=period).iloc[-1]
        except Exception as e:
            logger.error(f"Error calculating RSI for {ticker}: {e}")
            return None

    def get_macd(self, ticker: str) -> Dict[str, float]:
        """Get MACD indicator."""
        df = self.get_stock_data(ticker, period="6mo")
        if df.empty:
            return {}

        try:
            macd_line = ta.trend.macd(df["Close"])
            macd_signal = ta.trend.macd_signal(df["Close"])
            macd_diff = ta.trend.macd_diff(df["Close"])
            
            return {
                "macd": macd_line.iloc[-1],
                "signal": macd_signal.iloc[-1],
                "histogram": macd_diff.iloc[-1]
            }
        except Exception as e:
            logger.error(f"Error calculating MACD for {ticker}: {e}")
            return {}

    def get_bollinger_bands(self, ticker: str, window: int = 20, num_std: float = 2) -> Dict[str, float]:
        """Get Bollinger Bands."""
        df = self.get_stock_data(ticker, period="6mo")
        if df.empty or len(df) < window:
            return {}

        try:
            bb_high = ta.volatility.bollinger_hband(df["Close"], window=window, window_dev=num_std)
            bb_mid = ta.volatility.bollinger_mavg(df["Close"], window=window)
            bb_low = ta.volatility.bollinger_lband(df["Close"], window=window, window_dev=num_std)
            
            return {
                "upper": bb_high.iloc[-1],
                "middle": bb_mid.iloc[-1],
                "lower": bb_low.iloc[-1],
                "current": df["Close"].iloc[-1]
            }
        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands for {ticker}: {e}")
            return {}

    def get_atr(self, ticker: str, period: int = 14) -> Optional[float]:
        """Get Average True Range."""
        df = self.get_stock_data(ticker, period="6mo")
        if df.empty or len(df) < period:
            return None

        try:
            return ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=period).iloc[-1]
        except Exception as e:
            logger.error(f"Error calculating ATR for {ticker}: {e}")
            return None

    def get_volume_analysis(self, ticker: str) -> Dict[str, float]:
        """Analyze volume metrics."""
        df = self.get_stock_data(ticker, period="6mo")
        if df.empty:
            return {}

        try:
            avg_volume = df["Volume"].mean()
            current_volume = df["Volume"].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            
            return {
                "current_volume": current_volume,
                "average_volume": avg_volume,
                "volume_ratio": volume_ratio,
                "obv": ta.volume.on_balance_volume(df["Close"], df["Volume"]).iloc[-1]
            }
        except Exception as e:
            logger.error(f"Error analyzing volume for {ticker}: {e}")
            return {}

    def get_price_history(self, ticker: str, days: int = 30) -> Optional[pd.DataFrame]:
        """Get price history for the last N days."""
        df = self.get_stock_data(ticker, period="6mo")
        if df.empty:
            return None
        return df.tail(days)[["Close", "Volume"]]

    def get_correlation(self, tickers: List[str], period: str = "6mo") -> Optional[pd.DataFrame]:
        """Calculate correlation between multiple tickers."""
        try:
            data = {}
            for ticker in tickers:
                df = self.get_stock_data(ticker, period=period)
                if not df.empty:
                    data[ticker] = df["Close"]
            
            if not data:
                return None
            
            correlation_df = pd.DataFrame(data).corr()
            return correlation_df
        except Exception as e:
            logger.error(f"Error calculating correlation: {e}")
            return None
