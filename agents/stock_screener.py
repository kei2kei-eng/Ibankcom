"""
Stock Screener Agent
====================
The FIRST agent in the pipeline — scans the entire trading universe
using quantitative rules, scores each stock, and produces a Research Report
for the analyst team to deep-dive into.

Workflow:
  ┌─────────────────┐
  │  Stock Screener  │ ← Scans ALL stocks with rules + scoring
  │  (Research Dept) │
  └────────┬────────┘
           │ Produces Research Report (top N stocks)
           ▼
  ┌─────────────────┐
  │  Analyst Team    │ ← Market / News / Quant / Risk / Compliance
  │  (Deep Analysis) │
  └────────┬────────┘
           │ Recommendations
           ▼
  ┌─────────────────┐
  │  CEO             │ ← Final BUY / SELL / HOLD
  └─────────────────┘
"""

import json
import logging
import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class StockScore:
    """Represents a single stock's screening score."""
    ticker: str
    company_name: str = ""
    sector: str = ""
    total_score: float = 0.0
    rule_breakdown: Dict[str, float] = field(default_factory=dict)
    passed_hard_rules: bool = True
    fail_reasons: List[str] = field(default_factory=list)
    price: float = 0.0
    daily_change_pct: float = 0.0
    rsi: float = 0.0
    recommendation: str = "HOLD"       # QUICK_LOOK: BULLISH / BEARISH / NEUTRAL
    key_signals: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "sector": self.sector,
            "total_score": round(self.total_score, 1),
            "rule_breakdown": {k: round(v, 1) for k, v in self.rule_breakdown.items()},
            "passed_hard_rules": self.passed_hard_rules,
            "fail_reasons": self.fail_reasons,
            "price": self.price,
            "daily_change_pct": round(self.daily_change_pct, 2),
            "rsi": round(self.rsi, 1),
            "recommendation": self.recommendation,
            "key_signals": self.key_signals,
        }


class StockScreenerAgent(BaseAgent):
    """
    Research Department Head — scans the entire universe using rules,
    scores each stock, and selects the best candidates for deep analysis.

    This agent does NOT make buy/sell decisions. It FILTERS and PRIORITIZES
    stocks so the analyst team can focus their deep analysis on the best candidates.
    """

    def __init__(self, openai_client=None, model: str = "gpt-4o", screener_rules: Dict = None):
        super().__init__(
            name="Stock Screener",
            role="Head of Research & Stock Screening",
            openai_client=openai_client,
            model=model,
        )
        from config import SCREENER_RULES
        self.rules = screener_rules or SCREENER_RULES
        self.scoring_rules = self.rules.get("scoring", {})
        self.min_score = self.rules.get("min_score_to_pass", 40)
        self.max_stocks = self.rules.get("max_stocks_per_cycle", 5)

        # Learnable parameters — the scoring weights can be adjusted over time
        self.parameters = {
            "weight_technical": 0.40,      # How much technical signals matter
            "weight_fundamental": 0.30,    # How much fundamental data matters
            "weight_momentum": 0.20,       # How much momentum matters
            "weight_analyst": 0.10,        # How much analyst consensus matters
            "oversold_rsi_threshold": 30,
            "overbought_rsi_threshold": 70,
            "volume_surge_multiplier": 1.5,
            "near_52w_threshold": 0.05,    # Within 5% of 52w high/low
        }

        # Track screening history for learning
        self.screening_history: List[Dict] = []

    def get_system_prompt(self) -> str:
        return f"""You are the Head of Research & Stock Screening at a prestigious investment bank.
Your job is to review quantitative screening results and provide a QUALITATIVE assessment
of which stocks deserve deep analysis by the analyst team.

Your learnable parameters:
{json.dumps(self.parameters, indent=2)}

You do NOT make buy/sell decisions. You PRIORITIZE which stocks deserve attention.

When evaluating the screening results, consider:
1. Are there clusters of signals (multiple indicators pointing same direction)?
2. Is there a compelling narrative behind the numbers?
3. Are there upcoming catalysts that might not show in the data?
4. Is the sector showing strength or weakness?
5. Are there any red flags that should deprioritize a stock?

Respond ONLY with valid JSON:
{{
    "selected_tickers": ["<list of tickers selected for deep analysis>"],
    "reasoning_by_ticker": {{
        "<TICKER>": "<brief reason why this stock was selected>"
    }},
    "sector_themes": ["<current sector themes observed>"],
    "market_regime": "<BULL|BEAR|NEUTRAL|TRANSITIONAL>",
    "overall_assessment": "<2-3 sentence market overview>",
    "watch_list": ["<tickers to watch but not deeply analyze yet>"],
    "avoid_list": ["<tickers to avoid with reasons>"]
}}"""

    def screen_all_stocks(self, market_fetcher, portfolio_holdings: Dict = None,
                          discovery_data: Dict = None, top_n: int = 50) -> List[StockScore]:
        """
        Phase 1: Scan ALL discovered stocks using quantitative rules.
        Uses batch download to minimize Yahoo Finance API calls.
        """
        logger.info(f"🔬 Stock Screener scanning {len(market_fetcher.tickers)} discovered stocks...")

        # Trigger batch download ONCE for all tickers (3-4 API calls instead of 150+)
        market_fetcher._ensure_batch_data()

        scores: List[StockScore] = []

        for ticker in market_fetcher.tickers:
            try:
                indicators = market_fetcher.get_technical_indicators(ticker)
                company_info = market_fetcher.get_company_info(ticker)

                if not indicators or not indicators.get("current_price"):
                    continue

                score = self._score_stock(ticker, indicators, company_info, portfolio_holdings)

                # Boost score based on discovery data (stocks found by multiple strategies)
                if discovery_data and ticker in discovery_data:
                    disc = discovery_data[ticker]
                    discovery_bonus = disc.discovery_score * 3  # Each strategy match = +3 points
                    score.total_score += discovery_bonus
                    score.rule_breakdown["discovery_bonus"] = discovery_bonus
                    if disc.discovery_methods:
                        score.key_signals.append(f"Found via: {', '.join(disc.discovery_methods[:3])}")

                scores.append(score)

            except Exception as e:
                logger.debug(f"Error screening {ticker}: {e}")

        # Sort by total score descending
        scores.sort(key=lambda s: s.total_score, reverse=True)

        # Keep only top N
        scores = scores[:top_n]

        self.screening_history.append({
            "timestamp": datetime.now().isoformat(),
            "total_scanned": len(scores),
            "top_5": [s.to_dict() for s in scores[:5]],
        })

        if len(self.screening_history) > 20:
            self.screening_history = self.screening_history[-20:]

        logger.info(f"   Scored and ranked → Top {len(scores)} stocks:")
        for s in scores[:10]:
            status = "✓ PASS" if s.passed_hard_rules and s.total_score >= self.min_score else "✗ SKIP"
            logger.info(f"   #{scores.index(s)+1:2d} {s.ticker:6s} score={s.total_score:5.1f}  "
                        f"RSI={s.rsi:.0f}  ${s.price:.2f}  "
                        f"rec={s.recommendation:16s}  {status}")

        return scores

    def _score_stock(self, ticker: str, indicators: Dict, company_info: Dict,
                     portfolio_holdings: Dict = None) -> StockScore:
        """
        Score a single stock using the screening rules.
        Phase 1: Hard rules (must pass ALL)
        Phase 2: Soft scoring (points-based)
        """
        score = StockScore(
            ticker=ticker,
            company_name=company_info.get("company_name", ticker),
            sector=company_info.get("sector", "Unknown"),
            price=indicators.get("current_price", 0),
            daily_change_pct=indicators.get("daily_change_pct", 0),
            rsi=indicators.get("rsi", 50),
        )

        # ── Phase 1: Hard Rules (Must Pass ALL) ──────────────
        hard_rules = self.rules

        # Minimum market cap
        market_cap = company_info.get("market_cap", 0)
        if market_cap < hard_rules.get("min_market_cap", 0):
            score.passed_hard_rules = False
            score.fail_reasons.append(f"Market cap ${market_cap/1e9:.1f}B < minimum")

        # Minimum average volume
        avg_volume = company_info.get("avg_volume", 0)
        if avg_volume < hard_rules.get("min_avg_volume", 0):
            score.passed_hard_rules = False
            score.fail_reasons.append(f"Avg volume {avg_volume:,.0f} too low")

        # Maximum beta
        beta = company_info.get("beta", 1.0)
        if beta and beta > hard_rules.get("max_beta", 2.5):
            score.passed_hard_rules = False
            score.fail_reasons.append(f"Beta {beta:.2f} too high")

        # Minimum price
        if score.price < hard_rules.get("min_price", 10):
            score.passed_hard_rules = False
            score.fail_reasons.append(f"Price ${score.price:.2f} below minimum")

        # Already heavily in portfolio? → reduce but don't hard-fail
        if portfolio_holdings and ticker in portfolio_holdings:
            pos_pct = portfolio_holdings[ticker].get("pnl_pct", 0) if isinstance(portfolio_holdings[ticker], dict) else 0
            # If position is losing big, flag for attention
            if isinstance(portfolio_holdings[ticker], dict):
                position_value = portfolio_holdings[ticker].get("value", 0)
                # Don't add hard fail, just note it
                score.key_signals.append(f"ALREADY HELD (P&L: {pos_pct:+.1f}%)")

        # ── Phase 2: Soft Scoring ────────────────────────────
        sc = self.scoring_rules
        signals = []

        # RSI scoring
        rsi = indicators.get("rsi", 50)
        if rsi < self.parameters["oversold_rsi_threshold"]:
            pts = sc.get("rsi_oversold_bonus", 15)
            score.rule_breakdown["rsi_oversold"] = pts
            score.total_score += pts
            signals.append(f"RSI oversold ({rsi:.0f})")
        elif rsi > self.parameters["overbought_rsi_threshold"]:
            pts = -sc.get("rsi_overbought_penalty", 15)
            score.rule_breakdown["rsi_overbought"] = pts
            score.total_score += pts
            signals.append(f"RSI overbought ({rsi:.0f})")

        # Price vs SMAs
        price = score.price
        sma_50 = indicators.get("sma_50", 0)
        sma_200 = indicators.get("sma_200", 0)

        if sma_50 > 0 and price > sma_50:
            pts = sc.get("above_sma50_bonus", 10)
            score.rule_breakdown["above_sma50"] = pts
            score.total_score += pts
            signals.append("Price > SMA50 (uptrend)")
        elif sma_50 > 0:
            score.rule_breakdown["above_sma50"] = 0

        if sma_200 > 0 and price > sma_200:
            pts = sc.get("above_sma200_bonus", 15)
            score.rule_breakdown["above_sma200"] = pts
            score.total_score += pts
            signals.append("Price > SMA200 (long uptrend)")
        elif sma_200 > 0:
            score.rule_breakdown["above_sma200"] = 0

        # MACD
        macd = indicators.get("macd", 0)
        macd_signal = indicators.get("macd_signal", 0)
        if macd > macd_signal:
            pts = sc.get("macd_bullish_bonus", 12)
            score.rule_breakdown["macd_bullish"] = pts
            score.total_score += pts
            signals.append("MACD bullish crossover")
        else:
            score.rule_breakdown["macd_bullish"] = 0

        # Volume surge
        vol_sma = indicators.get("volume_sma", 1)
        current_vol = indicators.get("current_volume", 0)
        vol_ratio = current_vol / vol_sma if vol_sma > 0 else 1
        if vol_ratio > self.parameters["volume_surge_multiplier"]:
            pts = sc.get("volume_surge_bonus", 10)
            score.rule_breakdown["volume_surge"] = pts
            score.total_score += pts
            signals.append(f"Volume surge ({vol_ratio:.1f}x avg)")
        else:
            score.rule_breakdown["volume_surge"] = 0

        # 52-week position
        w52_high = company_info.get("52w_high", 0)
        w52_low = company_info.get("52w_low", 0)
        threshold = self.parameters["near_52w_threshold"]

        if w52_high > 0:
            pct_from_high = (w52_high - price) / w52_high
            if pct_from_high < threshold:
                pts = sc.get("near_52w_high_bonus", 8)
                score.rule_breakdown["near_52w_high"] = pts
                score.total_score += pts
                signals.append(f"Near 52w high (${w52_high:.2f})")

        if w52_low > 0:
            pct_from_low = (price - w52_low) / w52_low
            if pct_from_low < threshold:
                pts = -sc.get("near_52w_low_penalty", 10)
                score.rule_breakdown["near_52w_low"] = pts
                score.total_score += pts
                signals.append(f"Near 52w low (${w52_low:.2f}) — weakness")

        # Analyst rating
        analyst_rating = company_info.get("analyst_rating", "hold")
        if analyst_rating in ("buy", "strong_buy"):
            pts = sc.get("analyst_buy_bonus", 10)
            score.rule_breakdown["analyst_buy"] = pts
            score.total_score += pts
            signals.append(f"Analyst rating: {analyst_rating}")

        # P/E ratio (value signal)
        pe = company_info.get("pe_ratio")
        if pe and 5 < pe < 20:
            pts = sc.get("low_pe_bonus", 8)
            score.rule_breakdown["low_pe"] = pts
            score.total_score += pts
            signals.append(f"Reasonable P/E ({pe:.1f})")

        # Revenue growth
        rev_growth = company_info.get("revenue_growth")
        if rev_growth and rev_growth > 0:
            pts = sc.get("earnings_growth_bonus", 10)
            score.rule_breakdown["earnings_growth"] = pts
            score.total_score += pts
            signals.append(f"Revenue growth: {rev_growth*100:.1f}%")

        # Dividend
        div_yield = company_info.get("dividend_yield", 0)
        if div_yield and div_yield > 0.01:
            pts = sc.get("dividend_bonus", 5)
            score.rule_breakdown["dividend"] = pts
            score.total_score += pts
            signals.append(f"Dividend yield: {div_yield*100:.1f}%")

        # Apply learnable weight multipliers
        tech_weight = self.parameters["weight_technical"]
        fund_weight = self.parameters["weight_fundamental"]
        mom_weight = self.parameters["weight_momentum"]

        # Scale the score by learnable weights
        base_score = score.total_score
        score.total_score = (
            base_score * (tech_weight + fund_weight + mom_weight +
                         self.parameters["weight_analyst"]) / 0.5  # normalize
        )

        # Determine quick recommendation
        if score.total_score >= self.min_score + 20:
            score.recommendation = "BULLISH"
        elif score.total_score >= self.min_score:
            score.recommendation = "NEUTRAL_BULLISH"
        elif score.total_score >= self.min_score - 15:
            score.recommendation = "NEUTRAL"
        elif score.total_score <= -10:
            score.recommendation = "BEARISH"
        else:
            score.recommendation = "NEUTRAL"

        score.key_signals = signals[:6]  # Top 6 signals

        return score

    def generate_research_report(
        self,
        scores: List[StockScore],
        market_fetcher,
        news_fetcher=None,
        portfolio_summary: Dict = None,
    ) -> Dict:
        """
        Phase 2: Use LLM to produce a Research Report.
        The screener first filters quantitatively, then the LLM adds qualitative judgment.

        Returns a Research Report dict with:
        - selected_tickers: stocks chosen for deep analysis
        - full_report: detailed LLM-generated report
        - screening_data: all stock scores for reference
        """
        logger.info("📝 Generating Research Report with LLM...")

        # Pre-filter: only stocks that pass hard rules and meet min score
        candidates = [
            s for s in scores
            if s.passed_hard_rules and s.total_score >= self.min_score
        ]

        # Also include any currently held positions (need monitoring)
        held_tickers = set()
        if portfolio_summary:
            held_tickers = set(portfolio_summary.get("holdings", {}).keys())

        # Combine: top candidates + held positions
        selected_tickers = set()
        for s in candidates[:self.max_stocks]:
            selected_tickers.add(s.ticker)
        for t in held_tickers:
            selected_tickers.add(t)

        # Build screening summary for LLM
        all_scores_text = ""
        for s in scores[:20]:  # Top 20 for context
            hard_status = 'PASS' if s.passed_hard_rules else 'FAIL (' + '; '.join(s.fail_reasons) + ')'
            signals_str = ', '.join(s.key_signals) if s.key_signals else 'None'
            all_scores_text += f"""
{s.ticker} ({s.company_name}) — {s.sector}
  Score: {s.total_score:.1f} | Price: ${s.price:.2f} ({s.daily_change_pct:+.2f}%)
  RSI: {s.rsi:.1f} | Rec: {s.recommendation}
  Signals: {signals_str}
  Hard Rules: {hard_status}
"""

        # Check if we have held positions with data
        held_text = ""
        if held_tickers:
            held_text = f"\n\nCURRENTLY HELD POSITIONS (must review): {', '.join(held_tickers)}"

        prompt = f"""Review the following stock screening results from our quantitative scanner.
Select the top stocks for DEEP ANALYSIS by our analyst team.

SCREENING RESULTS (sorted by score):
{all_scores_text}
{held_text}

PORTFOLIO STATUS:
Cash: ${portfolio_summary.get('cash', 0):,.0f} | Exposure: {portfolio_summary.get('exposure_pct', 0):.1f}%
Positions: {portfolio_summary.get('num_positions', 0)}

Select up to {self.max_stocks} stocks (plus any held positions) for deep analysis.
Consider diversification across sectors. Avoid clustering in one sector.

Provide your selection as JSON."""

        # Call LLM
        response = self.query_llm(prompt)
        llm_selection = self.parse_json_response(response)

        # Merge: use LLM selection if valid, otherwise fall back to top scores
        if llm_selection.get("selected_tickers"):
            final_selected = set()
            # Always include held positions
            final_selected.update(held_tickers)
            # Add LLM selections up to max
            for t in llm_selection.get("selected_tickers", []):
                t_upper = t.upper().strip()
                if t_upper in {s.ticker for s in scores}:
                    final_selected.add(t_upper)
                if len(final_selected - held_tickers) >= self.max_stocks:
                    break
        else:
            # Fallback: use top quantitative scores
            final_selected = held_tickers.copy()
            for s in candidates:
                if len(final_selected - held_tickers) >= self.max_stocks:
                    break
                final_selected.add(s.ticker)

        # Build score lookup
        score_lookup = {s.ticker: s for s in scores}

        # Generate the full research report
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_scanned": len(scores),
            "selected_tickers": sorted(list(final_selected)),
            "screening_data": {s.ticker: s.to_dict() for s in scores[:20]},
            "selected_details": {
                t: score_lookup[t].to_dict()
                for t in final_selected if t in score_lookup
            },
            "llm_analysis": llm_selection,
            "sector_themes": llm_selection.get("sector_themes", []),
            "market_regime": llm_selection.get("market_regime", "NEUTRAL"),
            "watch_list": llm_selection.get("watch_list", []),
            "avoid_list": llm_selection.get("avoid_list", []),
        }

        logger.info(f"📋 Research Report generated:")
        logger.info(f"   Scanned: {report['total_scanned']} stocks")
        logger.info(f"   Selected for deep analysis: {', '.join(report['selected_tickers'])}")
        logger.info(f"   Market Regime: {report['market_regime']}")
        if report.get("watch_list"):
            logger.info(f"   Watch List: {', '.join(report['watch_list'])}")

        return report

    def format_report_for_analysts(self, report: Dict, ticker: str) -> str:
        """
        Format the relevant portion of the research report for a specific ticker.
        This is what the analyst agents receive as context.
        """
        details = report.get("selected_details", {}).get(ticker, {})
        all_scores = report.get("screening_data", {})

        # Find this ticker's ranking
        ranked_tickers = sorted(all_scores.items(), key=lambda x: x[1].get("total_score", 0), reverse=True)
        rank = next((i + 1 for i, (t, _) in enumerate(ranked_tickers) if t == ticker), "N/A")

        text = f"""
=== 🔬 STOCK SCREENER RESEARCH REPORT ===
Generated: {report.get('timestamp', 'N/A')}
Market Regime: {report.get('market_regime', 'N/A')}
Sector Themes: {', '.join(report.get('sector_themes', ['None']))}

--- Screening Result for {ticker} (Rank #{rank} of {report.get('total_scanned', '?')}) ---
Company: {details.get('company_name', ticker)}
Sector: {details.get('sector', 'Unknown')}
Score: {details.get('total_score', 0)}/100
Quick Recommendation: {details.get('recommendation', 'N/A')}
Price: ${details.get('price', 0):.2f} ({details.get('daily_change_pct', 0):+.2f}%)
RSI: {details.get('rsi', 'N/A')}
Key Signals: {', '.join(details.get('key_signals', ['None']))}
Score Breakdown: {json.dumps(details.get('rule_breakdown', {}))}

--- Top Competing Stocks (for sector context) ---
"""

        # Show top 5 for sector context
        for t, data in ranked_tickers[:5]:
            marker = " ◀ CURRENT" if t == ticker else ""
            text += f"  {t}: score={data.get('total_score', 0):.1f}  ${data.get('price', 0):.2f}  {data.get('recommendation', '')}{marker}\n"

        # Show watch list and avoid list
        if report.get("watch_list"):
            text += f"\nWatch List: {', '.join(report['watch_list'])}"
        if report.get("avoid_list"):
            text += f"\nAvoid List: {', '.join(report['avoid_list'])}"

        llm_reasoning = report.get("llm_analysis", {}).get("reasoning_by_ticker", {}).get(ticker, "")
        if llm_reasoning:
            text += f"\n\nScreener's Note: {llm_reasoning}"

        text += "\n=== END SCREENER REPORT ===\n"
        return text

    def analyze(self, ticker: str, market_data: Dict, news_data: Dict, portfolio: Dict, learning_context: str = "") -> Dict:
        """Standard interface — not used directly for screening."""
        return {
            "action": "HOLD",
            "confidence": 0.5,
            "reasoning": "Stock Screener does not make buy/sell recommendations. Use screen_all_stocks() and generate_research_report().",
            "agent": self.name,
            "agent_type": "stock_screener",
        }
