"""
Hourly Investment Report System
================================
Instead of auto-trading or a single daily report, the system:
  1. Scans the market every hour during trading hours
  2. Reviews how last hour's picks performed
  3. Learns from past decisions and adjusts agent weights
  4. Generates a fresh hourly report with updated analysis
  5. Sends it to you via Telegram
  6. YOU decide what to trade

Schedule: Runs every hour from 09:30 to 16:00 ET (market hours)
Each cycle:
  → Review previous hour's decisions vs actual market moves
  → Re-scan the market with updated data
  → Deep analyze top stocks with AI agents + learning context
  → Generate hourly report with "What Changed" section
  → Save + send report via Telegram
"""

import os
import sys
import json
import logging
import argparse
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Force unbuffered output for Docker / container logs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# ── Logging ──
LOG_DIR = os.getenv("LOG_DIR", ".")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "ai_ibank.log")),
    ],
)
logger = logging.getLogger("AI_iBank")

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from config import (
    OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL,
    INITIAL_CAPITAL, DISCOVERY_TOP_N, TRADING_SCHEDULE,
    FALLBACK_TICKERS,
)
from data.market_data import MarketDataFetcher
from data.news_data import NewsDataFetcher
from data.stock_discovery import StockDiscoveryEngine
from agents.stock_screener import StockScreenerAgent
from agents.market_analyst import MarketAnalystAgent
from agents.news_analyst import NewsAnalystAgent
from agents.quant_analyst import QuantAnalystAgent
from agents.risk_manager import RiskManagerAgent
from agents.ceo_agent import CEOAgent
from learning.decision_journal import DecisionJournal
from learning.reviewer import DecisionReviewer
from learning.adaptive_logic import AdaptiveLogicEngine
from portfolio.manager import PortfolioManager
from report_generator import HourlyReportGenerator
from hourly_tracker import HourlyTracker


def get_et_now():
    """Get current time in US/Eastern (market time)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("US/Eastern"))
    except ImportError:
        # Python < 3.9 fallback
        try:
            from dateutil.tz import gettz
            return datetime.now(gettz("US/Eastern"))
        except ImportError:
            logger.warning("⚠️  No timezone support — using system time. "
                          "Install: pip install tzdata")
            return datetime.now()


def is_market_hours():
    """Check if US stock market is currently open (ET)."""
    now = get_et_now()
    # Market open: Mon-Fri, 9:30 AM - 4:00 PM ET
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def minutes_until_market_open():
    """How many minutes until market opens."""
    now = get_et_now()
    # Next market open
    target = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    # Skip weekends
    while target.weekday() >= 5:
        target += timedelta(days=1)
    diff = (target - now).total_seconds() / 60
    return max(diff, 0)


class AIInvestmentBank:
    """
    Hourly Investment Report System.
    AI scans every hour → Reviews last hour → Learns → Reports to YOU → You trade.
    """

    def __init__(self, api_key=None, model=None, initial_capital=None):
        self.client = None
        if OpenAI and (api_key or OPENAI_API_KEY):
            self.client = OpenAI(
                api_key=api_key or OPENAI_API_KEY,
                base_url=OPENAI_BASE_URL,
            )
            logger.info("✅ OpenAI connected")
        else:
            logger.warning("⚠️  No API key — will use rules-only mode (no deep AI analysis)")

        self.model = model or OPENAI_MODEL
        self.news_fetcher = NewsDataFetcher(self.client)
        self.journal = DecisionJournal()
        self.reviewer = DecisionReviewer(self.journal, self.client, self.model)
        self.learner = AdaptiveLogicEngine(self.journal, self.client, self.model)
        self.portfolio = PortfolioManager(initial_capital=initial_capital or INITIAL_CAPITAL)
        self.discovery = StockDiscoveryEngine()
        self.market_data = MarketDataFetcher(FALLBACK_TICKERS)

        # AI Agents
        self.screener = StockScreenerAgent(self.client, self.model)
        self.agents = {
            "market_analyst": MarketAnalystAgent(self.client, self.model),
            "news_analyst": NewsAnalystAgent(self.client, self.model),
            "quant_analyst": QuantAnalystAgent(self.client, self.model),
            "risk_manager": RiskManagerAgent(self.client, self.model),
        }
        self.ceo = CEOAgent(self.client, self.model)

        # Report generator (hourly)
        self.report_gen = HourlyReportGenerator(self.client, self.model)

        # Hourly tracker — the core of continuous learning
        self.tracker = HourlyTracker(market_data_fetcher=self.market_data)

        # State
        self.discovered_tickers = []
        self.discovery_data = {}
        self.top_50 = []
        self.latest_report = None
        self._last_discovery_time = None
        self._cycle_number = 0

        # Ensure reports directory exists
        os.makedirs("reports", exist_ok=True)

        logger.info(f"🏦 AI Investment HOURLY Report System ready!")
        logger.info(f"   Model: {self.model}")
        logger.info(f"   ET Time now: {get_et_now().strftime('%Y-%m-%d %H:%M %A')}")
        logger.info(f"   Market {'OPEN' if is_market_hours() else 'CLOSED'}")

    # ── STEP 0: REVIEW PREVIOUS HOUR ──

    def review_previous_hour(self) -> Dict:
        """
        The first step of every hourly cycle: review what happened.
        - What did we recommend last hour?
        - How did those stocks actually move?
        - What should agents learn from this?
        """
        logger.info("📊 Step 0: Reviewing previous hour's decisions...")
        prev_review = self.tracker.review_previous_hour()
        multi_review = self.tracker.review_multi_hour(hours_back=4)
        learning_context = self.tracker.get_learning_context_for_agents()

        if prev_review.get("reviews"):
            logger.info(f"   → Previous hour: {prev_review['correct_count']}/{prev_review['total_count']} correct ({prev_review['accuracy']:.0%})")
            logger.info(f"   → Trend: {multi_review.get('trend', 'N/A')}")

        return {
            "prev_hour_review": prev_review,
            "multi_hour_review": multi_review,
            "learning_context": learning_context,
        }

    # ── STEP 1: DISCOVER (with caching) ──

    def run_discovery(self, force=False):
        # Discovery cache: 4 hours during market hours
        refresh_hours = 4
        if not force and self._last_discovery_time and \
                datetime.now() - self._last_discovery_time < timedelta(hours=refresh_hours):
            logger.info(f"🌍 Using cached discovery ({len(self.discovered_tickers)} stocks)")
            return self.discovered_tickers

        logger.info("🌍 Step 1: Discovering stocks from the market...")
        ticker_list, discovery_data = self.discovery.discover_all()
        self.discovered_tickers = ticker_list
        self.discovery_data = discovery_data
        self._last_discovery_time = datetime.now()
        self.market_data = MarketDataFetcher(ticker_list)
        self.tracker.market_data = self.market_data  # Update tracker with fresh data
        logger.info(f"   → Found {len(ticker_list)} stocks")
        # Cooldown: let Yahoo's rate limit reset before screening starts batch download
        logger.info("   ⏳ Cooling down 10s before screening (rate limit protection)...")
        time.sleep(10)
        return ticker_list

    # ── STEP 2: SCREEN ──

    def run_screening(self):
        logger.info(f"🔬 Step 2: Screening {len(self.discovered_tickers)} stocks → Top 50...")
        portfolio_summary = self.portfolio.get_portfolio_summary()
        scores = self.screener.screen_all_stocks(
            market_fetcher=self.market_data,
            portfolio_holdings=portfolio_summary.get("holdings", {}),
            discovery_data=self.discovery_data,
            top_n=DISCOVERY_TOP_N,
        )
        self.top_50 = scores
        self.latest_report = self.screener.generate_research_report(
            scores=scores,
            market_fetcher=self.market_data,
            portfolio_summary=portfolio_summary,
        )
        logger.info(f"   → Top 5 selected: {self.latest_report.get('selected_tickers', [])}")
        return self.latest_report

    # ── STEP 3: DEEP ANALYZE with learning ──

    def run_deep_analysis(self, report=None, learning_context=""):
        report = report or self.latest_report
        selected = report.get("selected_tickers", [])
        logger.info(f"🔍 Step 3: Deep analyzing {len(selected)} stocks with 6 AI agents + learning...")

        portfolio_summary = self.portfolio.get_portfolio_summary()
        analysis_results = {}

        for i, ticker in enumerate(selected):
            logger.info(f"   [{i+1}/{len(selected)}] Analyzing {ticker}...")

            # Get data
            indicators = self.market_data.get_technical_indicators(ticker)
            company_info = self.market_data.get_company_info(ticker)
            if not indicators:
                continue

            market_data = {"indicators": indicators, "company_info": company_info}

            # News (refreshed every hour)
            news_analysis = self.news_fetcher.get_news_analysis(
                ticker, company_info.get("company_name", ticker)
            )
            news_data = {"analysis": news_analysis}

            # Combined learning context: hourly tracker + decision journal
            journal_context = self.reviewer.get_learning_context_for_ticker(ticker)
            full_learning = f"HOURLY LEARNING:\n{learning_context}\n\nJOURNAL HISTORY:\n{journal_context}"

            screener_report = self.screener.format_report_for_analysts(report, ticker)

            # Each agent gives recommendation (with learning context)
            agent_recs = {}
            combined_context = f"LEARNING:\n{full_learning}\n\nSCREENER REPORT:\n{screener_report}"

            for agent_key, agent in self.agents.items():
                try:
                    rec = agent.analyze(
                        ticker=ticker, market_data=market_data,
                        news_data=news_data, portfolio=portfolio_summary,
                        learning_context=combined_context,
                    )
                    agent_recs[agent_key] = rec
                except Exception as e:
                    logger.error(f"   {agent.name} error: {e}")

            # CEO synthesizes (with learning)
            current_weights = self.learner.get_current_weights(self.agents)
            final = self.ceo.make_decision(
                ticker=ticker, agent_recommendations=agent_recs,
                market_data=market_data, portfolio=portfolio_summary,
                agent_weights=current_weights, learning_context=combined_context,
            )

            # Record for journal
            self.journal.record_decision(
                ticker=ticker, action=final.get("final_action", "HOLD"),
                quantity=0, price=indicators.get("current_price", 0),
                confidence=final.get("confidence", 0),
                final_decision=final, agent_recommendations=agent_recs,
                market_data=market_data, news_data=news_data,
                learning_context=full_learning, portfolio_snapshot=portfolio_summary,
            )

            # Record outcomes for previous decisions on this ticker
            self._update_outcome_for_ticker(ticker, indicators.get("current_price", 0))

            analysis_results[ticker] = {
                "final_decision": final,
                "agent_recommendations": agent_recs,
                "market_data": market_data,
                "news_analysis": news_analysis,
                "company_info": company_info,
                "indicators": indicators,
            }

        return analysis_results

    def _update_outcome_for_ticker(self, ticker: str, current_price: float):
        """Update outcome for the most recent decision on this ticker."""
        recent = self.journal.get_recent_decisions(limit=5, ticker=ticker)
        for d in recent:
            # Only update if no outcome yet and decision is from a previous cycle
            if d.get("outcome_label") is None or d.get("price_change_pct") is None:
                entry_price = d.get("price", 0)
                if entry_price > 0 and current_price > 0:
                    self.journal.record_outcome(
                        decision_id=d["id"],
                        ticker=ticker,
                        entry_price=entry_price,
                        current_price=current_price,
                    )

    # ── STEP 4: GENERATE REPORT ──

    def generate_hourly_report(self, analysis_results, review_data: Dict):
        """Generate the hourly report with learning feedback."""
        logger.info("📝 Step 4: Generating your hourly investment report...")

        report = self.report_gen.generate(
            top_50=self.top_50,
            screening_report=self.latest_report,
            analysis_results=analysis_results,
            portfolio=self.portfolio,
            prev_hour_review=review_data.get("prev_hour_review", {}),
            multi_hour_review=review_data.get("multi_hour_review", {}),
            learning_context=review_data.get("learning_context", ""),
        )
        self.report_gen.save(report)
        return report

    # ── STEP 5: SAVE TRACKER STATE ──

    def save_tracker_state(self, analysis_results, report):
        """Save this hour's decisions for next-hour comparison."""
        action_summary = report.get("action_summary", {})
        self.tracker.save_hour_decisions(analysis_results, action_summary)

    # ── STEP 6: LEARNING CYCLE ──

    def run_learning_cycle(self):
        """Run the adaptive learning engine to adjust agent weights."""
        logger.info("📚 Step 5: Running adaptive learning cycle...")
        feedback_list = self.reviewer.review_recent_decisions(hours_back=48)
        if feedback_list:
            for fb in feedback_list[:15]:
                fb["llm_review"] = self.reviewer.generate_llm_review(fb)
            self.learner.learn_from_feedback(feedback_list, self.agents)
            self.learner.learn_from_feedback(feedback_list, {"stock_screener": self.screener})
            logger.info("   → Agent weights and parameters adjusted")
        else:
            logger.info("   → No decisions to review yet")

    # ── FULL HOURLY PIPELINE ──

    def run_hourly_pipeline(self):
        """Run the complete hourly pipeline: review → discover → screen → analyze → report → learn."""
        self._cycle_number += 1
        start = datetime.now()
        logger.info(f"\n{'🦞'*30}")
        logger.info(f"🏦 HOURLY REPORT — Cycle #{self._cycle_number} — {start.strftime('%Y-%m-%d %H:%M')}")
        logger.info(f"{'🦞'*30}")

        # Step 0: Review previous hour's decisions
        review_data = self.review_previous_hour()

        # Step 1: Discover (cached for 4 hours)
        self.run_discovery(force=False)

        # Step 2: Screen
        report = self.run_screening()

        # Step 3: Deep analyze (with learning context)
        analysis = self.run_deep_analysis(
            report,
            learning_context=review_data.get("learning_context", ""),
        )

        # Step 4: Generate hourly report
        hourly_report = self.generate_hourly_report(analysis, review_data)

        # Step 5: Save tracker state for next hour
        self.save_tracker_state(analysis, hourly_report)

        # Step 6: Learning cycle (adjust agent weights)
        self.run_learning_cycle()

        elapsed = (datetime.now() - start).total_seconds()
        logger.info(f"✅ Hourly report #{self._cycle_number} generated in {elapsed:.0f}s")

        # Print summary
        self._print_summary(hourly_report, elapsed, review_data)

        # Send via Telegram (if configured)
        self.report_gen.send_report(hourly_report)

        return hourly_report

    def _print_summary(self, report, elapsed, review_data):
        prev = review_data.get("prev_hour_review", {})
        multi = review_data.get("multi_hour_review", {})
        summary = report.get("action_summary", {})

        print(f"\n{'='*60}", flush=True)
        print(f"🏦 HOURLY REPORT COMPLETE — Cycle #{self._cycle_number}", flush=True)
        print(f"{'='*60}", flush=True)
        print(f"   ⏱  Time: {elapsed:.0f}s", flush=True)
        print(f"   📊 Previous Hour Accuracy: {prev.get('accuracy', '—')}", flush=True)
        print(f"   📈 Multi-Hour Trend: {multi.get('trend', '—')}", flush=True)
        print(f"   🟢 BUY: {summary.get('total_buy', 0)} | 🔴 SELL: {summary.get('total_sell', 0)} | 🟡 HOLD: {summary.get('total_hold', 0)}", flush=True)
        print(f"   📄 Files: report_latest.html + report_latest.txt", flush=True)
        print(f"   📁 Archive: reports/report_{datetime.now().strftime('%Y%m%d_%H%M')}.html", flush=True)
        print(f"{'='*60}\n", flush=True)

    # ── SCHEDULER (no external dep, uses ET timezone) ──

    def start_hourly(self):
        """
        Run every hour during market hours (9:30 AM - 4:00 PM ET).
        Uses a simple loop with ET timezone — no schedule library needed.
        Handles: different server timezones, weekends, Docker restarts.
        """
        # Hourly schedule (ET)
        hourly_minutes = [35, 90, 150, 210, 270, 330, 390, 440]
        # 35min = 10:05, 90 = 11:00, 150 = 12:00, 210 = 13:00,
        # 270 = 14:00, 330 = 15:00, 390 = 16:00 (skip), 440 = beyond market
        # Simpler: run at minute 5 of every hour (10:05, 11:05, 12:05, ... 15:55)
        hourly_times_et = [
            (9, 35),   # 9:35 AM — just after market open
            (10, 5),
            (11, 5),
            (12, 5),
            (13, 5),
            (14, 5),
            (15, 5),
            (15, 50),  # Near market close
        ]

        et_now = get_et_now()
        print(f"\n{'🦞'*30}", flush=True)
        print(f"🏦 AI Investment Bank — HOURLY Report Mode", flush=True)
        print(f"{'🦞'*30}", flush=True)
        print(f"\n📍 Current ET time: {et_now.strftime('%Y-%m-%d %H:%M %A')}", flush=True)
        print(f"📊 Market {'OPEN' if is_market_hours() else 'CLOSED'}", flush=True)
        print(f"\n⏱  Reports will be generated at (ET):", flush=True)
        for h, m in hourly_times_et:
            print(f"   📅 {h:02d}:{m:02d} ET", flush=True)
        print(f"\n   First report generating now...\n", flush=True)

        # Run immediately on start (regardless of schedule)
        try:
            self.run_hourly_pipeline()
        except Exception as e:
            logger.error(f"Initial pipeline failed: {e}")

        print(f"\n   ⏳ Waiting for next scheduled time...\n", flush=True)

        # Main loop — no schedule library, uses ET time
        last_run_hour = -1
        try:
            while True:
                et_now = get_et_now()
                current_hour = et_now.hour
                current_minute = et_now.minute
                weekday = et_now.weekday()

                # Check if we should run this hour
                should_run = False

                # Only run on weekdays
                if weekday < 5:  # Mon=0 to Fri=4
                    # Check if current time matches any scheduled time
                    for h, m in hourly_times_et:
                        if current_hour == h and current_minute >= m and current_minute < m + 5:
                            # Only run once per scheduled slot
                            if last_run_hour != h * 100 + m:
                                should_run = True
                                last_run_hour = h * 100 + m
                                break

                if should_run:
                    logger.info(f"⏰ Scheduled run triggered at {et_now.strftime('%H:%M')} ET")
                    try:
                        self.run_hourly_pipeline()
                    except Exception as e:
                        logger.error(f"Pipeline error: {e}")
                        # Continue running even if one cycle fails

                # Sleep 60 seconds between checks
                time.sleep(60)

        except KeyboardInterrupt:
            print(f"\n🦞 Stopped after {self._cycle_number} hourly cycles.", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="🦞 AI Investment HOURLY Report (小龍蝦)"
    )
    parser.add_argument("--api-key", type=str, help="OpenAI API Key")
    parser.add_argument("--model", type=str, default="gpt-4o")
    parser.add_argument("--capital", type=float, default=1_000_000)
    parser.add_argument("--mode", choices=["report", "hourly", "interactive"],
                       default="report",
                       help="report=one report now, hourly=every hour during market, interactive=manual")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    bank = AIInvestmentBank(
        api_key=args.api_key, model=args.model,
        initial_capital=args.capital,
    )

    if args.mode == "report":
        # Generate one report now
        report = bank.run_hourly_pipeline()
        print(f"\n📄 Report saved! Open report_latest.html in your browser.", flush=True)

    elif args.mode == "hourly":
        # Run every hour during market hours
        bank.start_hourly()

    elif args.mode == "interactive":
        # Manual mode
        print(f"\n{'🦞'*30}", flush=True)
        print(f"🏦 AI Investment Bank — Interactive Mode (Hourly)", flush=True)
        print(f"{'🦞'*30}", flush=True)
        print(f"\nCommands:", flush=True)
        print(f"  report     — Run full hourly pipeline now", flush=True)
        print(f"  review     — Review previous hour's performance", flush=True)
        print(f"  discover   — Scan the market", flush=True)
        print(f"  screen     — Screen → Top 50", flush=True)
        print(f"  top50      — Show Top 50", flush=True)
        print(f"  analyze X  — Deep analyze one stock", flush=True)
        print(f"  learn      — Run learning cycle", flush=True)
        print(f"  status     — Show tracker status", flush=True)
        print(f"  portfolio  — Show portfolio", flush=True)
        print(f"  quit       — Exit\n", flush=True)

        while True:
            try:
                cmd = input("🦞 > ").strip()
                if not cmd:
                    continue
                parts = cmd.split()
                action = parts[0].lower()

                if action in ("quit", "exit"):
                    break
                elif action == "report":
                    bank.run_hourly_pipeline()
                elif action == "review":
                    review = bank.review_previous_hour()
                    prev = review["prev_hour_review"]
                    print(f"\n📊 Previous Hour Review:")
                    print(f"   Accuracy: {prev.get('accuracy', 0):.0%}")
                    for r in prev.get("reviews", []):
                        icon = "✅" if r["was_correct"] else "❌"
                        print(f"   {icon} {r['ticker']}: {r['prev_action']} @ ${r['prev_price']:.2f} → "
                              f"${r['current_price']:.2f} ({r['change_pct']:+.2f}%)")
                elif action == "discover":
                    bank.run_discovery(force=True)
                    print(f"✅ Found {len(bank.discovered_tickers)} stocks")
                elif action == "screen":
                    bank.run_discovery()
                    bank.run_screening()
                elif action == "top50":
                    for i, s in enumerate(bank.top_50[:20]):
                        print(f"  {i+1:2d}. {s.ticker:6s} {s.total_score:6.1f}  "
                              f"${s.price:9.2f}  RSI={s.rsi:3.0f}  {s.recommendation}")
                elif action == "analyze" and len(parts) > 1:
                    bank.run_discovery()
                    if not bank.latest_report:
                        bank.run_screening()
                    analysis = bank.run_deep_analysis(bank.latest_report)
                    ticker = parts[1].upper()
                    if ticker in analysis:
                        fd = analysis[ticker]["final_decision"]
                        print(f"\n{ticker}: {fd.get('final_action')} "
                              f"(confidence: {fd.get('confidence', 0):.2f})")
                        print(f"Reasoning: {fd.get('reasoning', '')[:500]}")
                    else:
                        print(f"{ticker} not in today's top picks. Try one of: "
                              f"{list(analysis.keys())}")
                elif action == "learn":
                    bank.run_learning_cycle()
                    print("✅ Learning cycle complete")
                elif action == "status":
                    tracker = bank.tracker
                    print(f"\n📊 Tracker Status:")
                    print(f"   History entries: {len(tracker.history)}")
                    if tracker.current_hour:
                        h = tracker.current_hour
                        print(f"   Current hour: {h.get('hour_label')} ({len(h.get('decisions', {}))} decisions)")
                        buys = h.get("summary", {}).get("buys", [])
                        sells = h.get("summary", {}).get("sells", [])
                        holds = h.get("summary", {}).get("holds", [])
                        print(f"   Current picks: BUY={buys} SELL={sells} HOLD={holds}")
                elif action == "portfolio":
                    print(bank.portfolio.print_portfolio())
                else:
                    print("Commands: report, review, discover, screen, top50, analyze X, learn, status, portfolio, quit")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    main()
