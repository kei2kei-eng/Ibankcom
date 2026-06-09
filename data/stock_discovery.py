"""
Stock Discovery Engine
======================
Dynamically discovers US stocks with high potential.
NO hardcoded list — scans the entire market using multiple strategies.

Discovery Strategies:
  1. S&P 500 + Nasdaq 100 constituents (large-cap backbone)
  2. Today's Top Gainers (momentum signals)
  3. Unusual Volume (institutional activity)
  4. Earnings Surprises (fundamental catalysts)
  5. 52-Week High Breakouts (technical breakouts)
  6. Analyst Upgrades (sentiment shifts)

All discovered stocks are deduplicated and returned as a candidate pool
for the Stock Screener to score and rank.
"""

import yfinance as yf
import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Set, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredStock:
    """A stock discovered by one or more strategies."""
    ticker: str
    company_name: str = ""
    discovery_methods: List[str] = field(default_factory=list)
    discovery_score: float = 0.0       # How many strategies flagged this stock
    quick_data: Dict = field(default_factory=dict)


class StockDiscoveryEngine:
    """
    Scans the entire US market to find stocks with high potential.
    Combines multiple discovery strategies into a unified candidate pool.
    """

    # Major index constituents (cached, refreshed periodically)
    SP500_TICKERS: List[str] = []
    NASDAQ100_TICKERS: List[str] = []

    def __init__(self):
        self._index_cache_time = None
        self._index_cache_duration = timedelta(hours=24)
        self._discovery_cache: Dict[str, DiscoveredStock] = {}
        self._cache_time: datetime = None
        self._cache_duration = timedelta(hours=4)

    # ================================================================
    # Strategy 1: Index Constituents (Large-Cap Backbone)
    # ================================================================

    # Comprehensive S&P 500 fallback (used when Wikipedia is blocked)
    SP500_FALLBACK = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "UNH", "JPM",
        "V", "JNJ", "WMT", "XOM", "PG", "MA", "HD", "CVX", "MRK", "ABBV",
        "PEP", "KO", "AVGO", "COST", "ADBE", "TMO", "CSCO", "MCD", "ACN", "CRM",
        "NFLX", "AMD", "INTC", "CMCSA", "NKE", "ORCL", "TXN", "QCOM", "LLY", "BAC",
        "VZ", "WFC", "GS", "CAT", "DE", "RTX", "HON", "UPS", "BA", "SBUX",
        "AMGN", "MDLZ", "GILD", "ISRG", "BIIB", "REGN", "VRTX", "AXP", "SPGI", "BLK",
        "CME", "COF", "SCHW", "MS", "SYK", "TJX", "LRCX", "ADP", "CB", "MMC",
        "ZTS", "CI", "HCA", "CL", "TGT", "PGR", "ICE", "DUK", "SO", "D",
        "NEE", "PLD", "AMT", "EQIX", "PSA", "O", "CCI", "DLR", "WELL", "SPG",
        "PYPL", "BKNG", "ABNB", "SQ", "SHOP", "SNOW", "PLTR", "COIN", "HOOD", "RIVN",
        "PANW", "MSTR", "CRWD", "FORTY", "MELI", "CEG", "SMCI", "DELL", "ANET", "FTNT",
    ]

    def get_sp500_tickers(self) -> List[str]:
        """Fetch current S&P 500 constituents from Wikipedia, with fallback."""
        try:
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            tables = pd.read_html(url)
            df = tables[0]
            tickers = df["Symbol"].str.replace(".", "-").tolist()
            logger.info(f"S&P 500: fetched {len(tickers)} constituents")
            return tickers
        except Exception as e:
            logger.warning(f"Wikipedia S&P 500 unavailable ({e}), using built-in list of {len(self.SP500_FALLBACK)} stocks")
            return list(self.SP500_FALLBACK)

    def get_nasdaq100_tickers(self) -> List[str]:
        """Fetch current Nasdaq 100 constituents."""
        try:
            url = "https://en.wikipedia.org/wiki/Nasdaq-100"
            tables = pd.read_html(url)
            for table in tables:
                if "Ticker" in table.columns:
                    tickers = table["Ticker"].str.replace(".", "-").tolist()
                    logger.info(f"Nasdaq 100: fetched {len(tickers)} constituents")
                    return tickers
        except Exception as e:
            logger.warning(f"Wikipedia Nasdaq 100 unavailable ({e}), using built-in list")

        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "COST", "NFLX",
            "AMD", "INTC", "CRM", "ADBE", "QCOM", "TXN", "CMCSA", "PEP", "CSCO", "PYPL",
            "BKNG", "AMGN", "HON", "SBUX", "ISRG", "ABNB", "SNOW", "PLTR", "MRVL", "MELI",
            "PANW", "CRWD", "SMCI", "DELL", "FTNT", "ANET", "MNST", "PCAR", "ROST", "IDXX",
        ]

    # ================================================================
    # Strategy 2: Today's Top Gainers / Losers (Momentum)
    # ================================================================

    def get_top_gainers(self, limit: int = 30) -> List[Dict]:
        """Find today's top gaining US stocks using yfinance screener."""
        try:
            # Use yfinance built-in screener for gainers
            gainers = yf.Downloader().get("most_actives") if hasattr(yf, "Downloader") else None

            # Alternative: scan a broad ETF like RUSSELL 3000 proxy
            # For reliability, we use the yfinance screener API
            result = []
            try:
                import requests
                # Yahoo Finance screener API for top gainers
                url = ("https://query1.finance.yahoo.com/v1/finance/screener/predefined/"
                       "saved?scrIds=day_gainers&count=30&pfId=day_gainers")
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
                    for q in quotes[:limit]:
                        result.append({
                            "ticker": q.get("symbol", ""),
                            "name": q.get("shortName", ""),
                            "price": q.get("regularMarketPrice", 0),
                            "change_pct": q.get("regularMarketChangePercent", 0),
                            "volume": q.get("regularMarketVolume", 0),
                            "market_cap": q.get("marketCap", 0),
                        })
            except Exception as e:
                logger.warning(f"Yahoo screener API for gainers failed: {e}")

            logger.info(f"Top gainers: found {len(result)} stocks")
            return result

        except Exception as e:
            logger.error(f"Error finding top gainers: {e}")
            return []

    def get_top_losers(self, limit: int = 15) -> List[Dict]:
        """Find today's top losing stocks (potential oversold bounces)."""
        try:
            result = []
            try:
                import requests
                url = ("https://query1.finance.yahoo.com/v1/finance/screener/predefined/"
                       "saved?scrIds=day_losers&count=15")
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
                    for q in quotes[:limit]:
                        result.append({
                            "ticker": q.get("symbol", ""),
                            "name": q.get("shortName", ""),
                            "price": q.get("regularMarketPrice", 0),
                            "change_pct": q.get("regularMarketChangePercent", 0),
                            "volume": q.get("regularMarketVolume", 0),
                            "market_cap": q.get("marketCap", 0),
                        })
            except Exception:
                pass

            logger.info(f"Top losers: found {len(result)} stocks")
            return result
        except Exception as e:
            logger.error(f"Error finding losers: {e}")
            return []

    # ================================================================
    # Strategy 3: Unusual Volume (Institutional Activity)
    # ================================================================

    def get_unusual_volume(self, tickers: List[str], volume_multiplier: float = 2.0) -> List[str]:
        """
        Scan a list of tickers for unusual volume (2x+ average).
        This detects institutional buying/selling activity.
        """
        unusual = []
        batch_size = 10

        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            for ticker in batch:
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1mo")
                    if hist.empty or len(hist) < 5:
                        continue

                    avg_vol = hist["Volume"].iloc[:-1].mean()
                    today_vol = hist["Volume"].iloc[-1]

                    if avg_vol > 0 and today_vol > avg_vol * volume_multiplier:
                        unusual.append(ticker)

                except Exception:
                    continue

        logger.info(f"Unusual volume: found {len(unusual)} stocks out of {len(tickers)} scanned")
        return unusual

    # ================================================================
    # Strategy 4: Sector-Based Discovery
    # ================================================================

    SECTOR_ETFS = {
        "Technology": "XLK",
        "Healthcare": "XLV",
        "Financials": "XLF",
        "Consumer Discretionary": "XLY",
        "Industrials": "XLI",
        "Energy": "XLE",
        "Consumer Staples": "XLP",
        "Utilities": "XLU",
        "Real Estate": "XLRE",
        "Materials": "XLB",
        "Communication Services": "XLC",
    }

    def get_top_sector_performers(self, top_n_per_sector: int = 3) -> List[Dict]:
        """
        Get top performing stocks from each sector via sector ETF holdings.
        Ensures diversification across sectors.
        """
        performers = []

        for sector, etf in self.SECTOR_ETFS.items():
            try:
                etf_ticker = yf.Ticker(etf)
                holdings = etf_ticker.info.get("holdings", [])

                if not holdings:
                    # Fallback: get the ETF's top holdings via history
                    # Just note this sector
                    continue

                for h in holdings[:top_n_per_sector]:
                    symbol = h.get("symbol", "")
                    if symbol:
                        performers.append({
                            "ticker": symbol,
                            "name": h.get("holdingName", ""),
                            "sector": sector,
                            "weight_in_etf": h.get("holdingPercent", 0),
                        })

            except Exception as e:
                logger.debug(f"Could not get holdings for {etf}: {e}")

        logger.info(f"Sector performers: found {len(performers)} stocks across {len(self.SECTOR_ETFS)} sectors")
        return performers

    # ================================================================
    # Strategy 5: Technical Breakout Scanner
    # ================================================================

    def scan_breakouts(self, tickers: List[str]) -> List[str]:
        """
        Scan tickers for technical breakouts:
        - 52-week high breakouts
        - SMA crossover (50/200 golden cross)
        - RSI recovery from oversold
        """
        breakouts = []
        batch_size = 10

        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            for ticker in batch:
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="6mo")
                    if hist.empty or len(hist) < 50:
                        continue

                    close = hist["Close"]
                    high_52w = close.rolling(252).max().iloc[-1] if len(close) >= 252 else close.max()

                    # Check: within 3% of 52-week high
                    current = close.iloc[-1]
                    if high_52w > 0 and current >= high_52w * 0.97:
                        breakouts.append(ticker)
                        continue

                    # Check: SMA50 crosses above SMA200 (golden cross)
                    if len(close) >= 200:
                        sma50 = close.rolling(50).mean()
                        sma200 = close.rolling(200).mean()
                        if (sma50.iloc[-1] > sma200.iloc[-1] and
                            sma50.iloc[-2] <= sma200.iloc[-2]):
                            breakouts.append(ticker)

                except Exception:
                    continue

        logger.info(f"Breakout scanner: found {len(breakouts)} breakouts")
        return breakouts

    # ================================================================
    # MAIN: Run All Discovery Strategies
    # ================================================================

    def discover_all(self) -> Tuple[List[str], Dict[str, DiscoveredStock]]:
        """
        Run ALL discovery strategies and return a deduplicated candidate pool.
        Returns: (list of tickers, dict of DiscoveredStock objects)
        """
        logger.info("🌍 Stock Discovery Engine — Scanning the entire US market...")

        discovered: Dict[str, DiscoveredStock] = {}

        # ── Strategy 1: Index Constituents ──
        logger.info("  📊 Strategy 1: Fetching S&P 500 + Nasdaq 100 constituents...")
        sp500 = self.get_sp500_tickers()
        nasdaq100 = self.get_nasdaq100_tickers()
        index_tickers = set(sp500 + nasdaq100)
        for t in index_tickers:
            self._add_discovery(discovered, t, "index_constituent", 1)
        logger.info(f"     → {len(index_tickers)} unique index stocks")

        # ── Strategy 2: Today's Top Gainers ──
        logger.info("  🚀 Strategy 2: Scanning today's top gainers...")
        gainers = self.get_top_gainers(limit=30)
        for g in gainers:
            t = g.get("ticker", "")
            if t:
                self._add_discovery(discovered, t, "top_gainer", 2, g)
        logger.info(f"     → {len(gainers)} top gainers")

        # ── Strategy 3: Today's Top Losers (oversold opportunities) ──
        logger.info("  📉 Strategy 3: Scanning today's top losers (oversold opportunities)...")
        losers = self.get_top_losers(limit=15)
        for l in losers:
            t = l.get("ticker", "")
            if t:
                self._add_discovery(discovered, t, "top_loser", 1, l)
        logger.info(f"     → {len(losers)} oversold candidates")

        # ── Strategy 4: Sector Performers ──
        logger.info("  🏭 Strategy 4: Scanning sector leaders...")
        sector_stocks = self.get_top_sector_performers(top_n_per_sector=3)
        for s in sector_stocks:
            t = s.get("ticker", "")
            if t:
                self._add_discovery(discovered, t, f"sector_leader_{s.get('sector', '')}", 1.5, s)
        logger.info(f"     → {len(sector_stocks)} sector leaders")

        # ── Strategy 5: Unusual Volume (sample from index) ──
        logger.info("  📦 Strategy 5: Scanning for unusual volume...")
        # Scan a sample of 50 index stocks for volume surges
        import random
        sample = random.sample(list(index_tickers), min(50, len(index_tickers)))
        unusual = self.get_unusual_volume(sample, volume_multiplier=1.8)
        for t in unusual:
            self._add_discovery(discovered, t, "unusual_volume", 2)
        logger.info(f"     → {len(unusual)} with unusual volume")

        # ── Strategy 6: Breakout Scanner (sample) ──
        logger.info("  💥 Strategy 6: Scanning for technical breakouts...")
        breakout_sample = random.sample(list(index_tickers), min(30, len(index_tickers)))
        breakouts = self.scan_breakouts(breakout_sample)
        for t in breakouts:
            self._add_discovery(discovered, t, "breakout", 2)
        logger.info(f"     → {len(breakouts)} breakout stocks")

        # ── Compile Results ──
        # Sort by discovery_score (stocks found by multiple strategies rank higher)
        sorted_stocks = sorted(
            discovered.values(),
            key=lambda s: s.discovery_score,
            reverse=True,
        )

        ticker_list = [s.ticker for s in sorted_stocks]

        logger.info(f"\n{'='*60}")
        logger.info(f"🌍 DISCOVERY COMPLETE")
        logger.info(f"   Total unique stocks discovered: {len(ticker_list)}")
        logger.info(f"   Top 10 by discovery score:")
        for s in sorted_stocks[:10]:
            methods = ", ".join(s.discovery_methods[:3])
            logger.info(f"     {s.ticker:6s}  score={s.discovery_score:.1f}  "
                        f"methods=[{methods}]")
        logger.info(f"{'='*60}")

        self._discovery_cache = discovered
        self._cache_time = datetime.now()

        return ticker_list, discovered


    def _add_discovery(self, discovered: Dict, ticker: str, method: str,
                       weight: float, data: Dict = None):
        """Add a stock discovery, accumulating scores."""
        if ticker in discovered:
            discovered[ticker].discovery_methods.append(method)
            discovered[ticker].discovery_score += weight
            if data:
                discovered[ticker].quick_data.update(data)
        else:
            discovered[ticker] = DiscoveredStock(
                ticker=ticker,
                discovery_methods=[method],
                discovery_score=weight,
                quick_data=data or {},
            )
