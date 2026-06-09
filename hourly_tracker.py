"""
Hourly Tracker
==============
Tracks decisions from previous hours and compares them with current market data.
This enables the "learn from the last hour" mechanism:
  - What did we recommend last hour?
  - How did those stocks actually move?
  - What should we learn / adjust?
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

TRACKER_FILE = "hourly_tracker_state.json"


class HourlyTracker:
    """
    Persists the state between hourly runs.
    Each hour it:
      1. Loads previous hour's decisions
      2. Fetches current prices for those tickers
      3. Generates performance feedback
      4. Saves current hour's decisions for next cycle
    """

    def __init__(self, market_data_fetcher=None):
        self.state_file = TRACKER_FILE
        self.market_data = market_data_fetcher
        self.history: List[Dict] = []  # list of past hourly snapshots
        self.current_hour: Optional[Dict] = None
        self._load_state()

    def _load_state(self):
        """Load tracker state from disk."""
        path = Path(self.state_file)
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                self.history = data.get("history", [])
                self.current_hour = data.get("current_hour")
                logger.info(f"📊 Loaded tracker: {len(self.history)} past hours")
            except Exception as e:
                logger.warning(f"Tracker state load failed: {e}")
                self.history = []
                self.current_hour = None

    def _save_state(self):
        """Persist tracker state to disk."""
        data = {
            "history": self.history[-48:],  # keep last 48 hours (6 trading days)
            "current_hour": self.current_hour,
            "last_updated": datetime.now().isoformat(),
        }
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def save_hour_decisions(self, decisions: Dict[str, Dict], report_summary: Dict):
        """
        Save this hour's decisions for next-hour comparison.

        Args:
            decisions: {ticker: {final_decision, indicators, ...}} from analysis_results
            report_summary: the action_summary dict from report
        """
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "hour_label": datetime.now().strftime("%H:%M"),
            "decisions": {},
            "summary": {
                "buys": [b["ticker"] for b in report_summary.get("buy_recommendations", [])],
                "sells": [s["ticker"] for s in report_summary.get("sell_recommendations", [])],
                "holds": [h["ticker"] for h in report_summary.get("hold_recommendations", [])],
            },
        }

        for ticker, data in decisions.items():
            fd = data.get("final_decision", {})
            indicators = data.get("indicators", {})
            snapshot["decisions"][ticker] = {
                "action": fd.get("final_action", "HOLD"),
                "confidence": fd.get("confidence", 0),
                "target_price": fd.get("target_price"),
                "stop_loss": fd.get("stop_loss"),
                "price_at_analysis": indicators.get("current_price", 0),
                "reasoning": fd.get("reasoning", "")[:300],
            }

        # Archive previous current_hour to history
        if self.current_hour:
            self.history.append(self.current_hour)

        self.current_hour = snapshot
        self._save_state()
        logger.info(f"📊 Tracker saved: {len(snapshot['decisions'])} decisions for {snapshot['hour_label']}")

    def review_previous_hour(self) -> Dict:
        """
        Compare previous hour's decisions with current market data.

        Returns:
            {
                "timestamp": when the previous hour ran,
                "reviews": [
                    {
                        "ticker": "AAPL",
                        "prev_action": "BUY",
                        "prev_price": 150.00,
                        "current_price": 152.50,
                        "change_pct": +1.67,
                        "was_correct": True,
                        "reasoning": "..."
                    },
                    ...
                ],
                "accuracy": 0.60,
                "learning_notes": "...",
                "top_performers": [...],
                "worst_performers": [...],
            }
        """
        if not self.history:
            return {
                "timestamp": None,
                "reviews": [],
                "accuracy": 0,
                "learning_notes": "No previous hourly data to compare. This is the first run.",
                "top_performers": [],
                "worst_performers": [],
            }

        # Get the most recent past hour
        prev = self.history[-1]
        reviews = []
        correct_count = 0
        total_count = 0

        for ticker, prev_decision in prev.get("decisions", {}).items():
            prev_price = prev_decision.get("price_at_analysis", 0)
            prev_action = prev_decision.get("action", "HOLD")
            prev_target = prev_decision.get("target_price")
            prev_stop = prev_decision.get("stop_loss")

            if prev_price <= 0:
                continue

            # Fetch current price
            current_price = self._get_current_price(ticker)
            if current_price is None or current_price <= 0:
                continue

            change_pct = ((current_price - prev_price) / prev_price) * 100
            was_correct = self._evaluate_correctness(prev_action, change_pct)

            if was_correct:
                correct_count += 1
            total_count += 1

            # Check if target/stop was hit
            target_hit = False
            stop_hit = False
            if prev_target and prev_action == "BUY":
                target_hit = current_price >= prev_target
            if prev_stop and prev_action == "BUY":
                stop_hit = current_price <= prev_stop

            reviews.append({
                "ticker": ticker,
                "prev_action": prev_action,
                "prev_price": round(prev_price, 2),
                "current_price": round(current_price, 2),
                "change_pct": round(change_pct, 2),
                "was_correct": was_correct,
                "target_hit": target_hit,
                "stop_hit": stop_hit,
                "prev_confidence": round(prev_decision.get("confidence", 0), 2),
                "reasoning": prev_decision.get("reasoning", "")[:200],
            })

        accuracy = correct_count / max(total_count, 1)

        # Sort by performance
        sorted_reviews = sorted(reviews, key=lambda x: x["change_pct"], reverse=True)
        top_performers = sorted_reviews[:3]
        worst_performers = sorted_reviews[-3:] if len(sorted_reviews) > 3 else []

        # Generate learning notes
        learning_notes = self._generate_learning_notes(reviews, accuracy)

        result = {
            "timestamp": prev.get("timestamp"),
            "hour_label": prev.get("hour_label", "?"),
            "reviews": reviews,
            "accuracy": round(accuracy, 2),
            "correct_count": correct_count,
            "total_count": total_count,
            "learning_notes": learning_notes,
            "top_performers": top_performers,
            "worst_performers": worst_performers,
        }

        logger.info(f"📊 Previous hour review: {correct_count}/{total_count} correct ({accuracy:.0%})")
        return result

    def review_multi_hour(self, hours_back: int = 4) -> Dict:
        """
        Review performance over the last N hours for deeper learning.
        """
        if len(self.history) < 1:
            return {"trend": "no_data", "accuracy_trend": [], "learning_insights": "Not enough data yet."}

        recent = self.history[-hours_back:]
        accuracy_trend = []

        for hour_snapshot in recent:
            correct = 0
            total = 0
            for ticker, decision in hour_snapshot.get("decisions", {}).items():
                prev_price = decision.get("price_at_analysis", 0)
                action = decision.get("action", "HOLD")
                current_price = self._get_current_price(ticker)
                if prev_price > 0 and current_price and current_price > 0:
                    change_pct = ((current_price - prev_price) / prev_price) * 100
                    if self._evaluate_correctness(action, change_pct):
                        correct += 1
                    total += 1
            accuracy_trend.append({
                "hour": hour_snapshot.get("hour_label", "?"),
                "accuracy": correct / max(total, 1),
                "total": total,
            })

        # Determine trend
        if len(accuracy_trend) >= 2:
            recent_acc = accuracy_trend[-1]["accuracy"]
            older_acc = accuracy_trend[0]["accuracy"]
            if recent_acc > older_acc + 0.1:
                trend = "improving"
            elif recent_acc < older_acc - 0.1:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return {
            "trend": trend,
            "accuracy_trend": accuracy_trend,
            "learning_insights": self._generate_trend_insights(trend, accuracy_trend),
        }

    def get_learning_context_for_agents(self) -> str:
        """
        Generate learning context string to inject into agent prompts.
        This tells agents how their previous hour's recommendations performed.
        """
        review = self.review_previous_hour()

        if not review["reviews"]:
            return "No previous hour data available for learning."

        lines = [
            f"=== HOURLY LEARNING FEEDBACK ===",
            f"Previous Hour ({review.get('hour_label', 'N/A')}):",
            f"Overall Accuracy: {review['accuracy']:.0%} ({review['correct_count']}/{review['total_count']} correct)",
            "",
        ]

        for r in review["reviews"]:
            status = "✅" if r["was_correct"] else "❌"
            lines.append(
                f"  {status} {r['ticker']}: Recommended {r['prev_action']} @ ${r['prev_price']:.2f} "
                f"→ Now ${r['current_price']:.2f} ({r['change_pct']:+.2f}%)"
            )
            if r.get("target_hit"):
                lines.append(f"      🎯 Target price hit!")
            if r.get("stop_hit"):
                lines.append(f"      🛑 Stop loss hit!")

        if review.get("top_performers"):
            best = review["top_performers"][0]
            lines.append(f"\n  Best pick: {best['ticker']} ({best['change_pct']:+.2f}%)")

        if review.get("worst_performers"):
            worst = review["worst_performers"][-1]
            lines.append(f"  Worst pick: {worst['ticker']} ({worst['change_pct']:+.2f}%)")

        lines.append(f"\nKey Insight: {review['learning_notes']}")

        # Multi-hour trend
        multi = self.review_multi_hour(hours_back=4)
        if multi.get("accuracy_trend"):
            lines.append(f"\nMulti-Hour Trend: {multi['trend']}")
            lines.append(f"  {multi['learning_insights']}")

        return "\n".join(lines)

    def _get_current_price(self, ticker: str) -> Optional[float]:
        """Get current price for a ticker."""
        if self.market_data:
            try:
                indicators = self.market_data.get_technical_indicators(ticker)
                if indicators:
                    return indicators.get("current_price")
            except Exception as e:
                logger.debug(f"Price fetch failed for {ticker}: {e}")
        return None

    def _evaluate_correctness(self, action: str, change_pct: float) -> bool:
        """Evaluate if a decision was correct given the price movement."""
        if action == "BUY":
            return change_pct > 0.3  # Threshold for a good buy
        elif action == "SELL":
            return change_pct < -0.3  # Threshold for a good sell
        else:  # HOLD
            return abs(change_pct) < 2.0  # Hold was right if no big move

    def _generate_learning_notes(self, reviews: List[Dict], accuracy: float) -> str:
        """Generate actionable learning notes from the reviews."""
        if not reviews:
            return "No decisions to review."

        buys = [r for r in reviews if r["prev_action"] == "BUY"]
        sells = [r for r in reviews if r["prev_action"] == "SELL"]
        holds = [r for r in reviews if r["prev_action"] == "HOLD"]

        notes = []

        if buys:
            buy_acc = sum(1 for b in buys if b["was_correct"]) / max(len(buys), 1)
            avg_return = sum(b["change_pct"] for b in buys) / max(len(buys), 1)
            notes.append(f"BUY accuracy: {buy_acc:.0%}, avg return: {avg_return:+.2f}%")

        if sells:
            sell_acc = sum(1 for s in sells if s["was_correct"]) / max(len(sells), 1)
            notes.append(f"SELL accuracy: {sell_acc:.0%}")

        if accuracy > 0.7:
            notes.append("Good hour — agents are reading the market well. Consider maintaining current strategy.")
        elif accuracy < 0.4:
            notes.append("Poor hour — market conditions may have shifted. Agents should be more cautious and review thresholds.")
        else:
            notes.append("Mixed results — continue monitoring for pattern changes.")

        return " | ".join(notes)

    def _generate_trend_insights(self, trend: str, accuracy_trend: List[Dict]) -> str:
        """Generate insights from multi-hour accuracy trends."""
        if trend == "improving":
            return "Accuracy is improving — current learning adjustments are working. Keep current agent weights."
        elif trend == "declining":
            return "Accuracy is declining — market regime may have changed. Agents should increase caution and tighten thresholds."
        elif trend == "stable":
            return "Accuracy is stable — system is performing consistently."
        else:
            return "Building baseline data — need more hours to establish trends."
