"""
Decision Reviewer
=================
Reviews past decisions against actual market outcomes.
Each agent reviews its own past decisions to learn from mistakes.
"""

import json
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from .decision_journal import DecisionJournal

logger = logging.getLogger(__name__)


class DecisionReviewer:
    """
    Periodically reviews past decisions and evaluates whether they were correct.
    Generates feedback for the Adaptive Logic Engine to adjust agent parameters.
    """

    def __init__(self, journal: DecisionJournal, openai_client=None, model: str = "gpt-4o"):
        self.journal = journal
        self.client = openai_client
        self.model = model

    def review_recent_decisions(self, hours_back: int = 48) -> List[Dict]:
        """
        Review decisions made in the last N hours and compare with outcomes.
        Returns feedback for each reviewed decision.
        """
        decisions = self.journal.get_recent_decisions(limit=50)
        feedback_list = []

        cutoff = (datetime.now() - timedelta(hours=hours_back)).isoformat()

        for decision in decisions:
            if decision["timestamp"] < cutoff:
                continue

            decision_id = decision["id"]
            full_decision = self.journal.get_decision_for_review(decision_id)

            if not full_decision:
                continue

            feedback = self._evaluate_decision(full_decision)
            if feedback:
                feedback_list.append(feedback)

        logger.info(f"Reviewed {len(feedback_list)} recent decisions")
        return feedback_list

    def _evaluate_decision(self, decision: Dict) -> Optional[Dict]:
        """
        Evaluate a single decision against its outcome.
        """
        outcome = decision.get("outcome")
        if not outcome:
            return None

        ticker = decision["ticker"]
        action = decision["action"]
        entry_price = decision["price"]
        current_price = outcome.get("current_price", entry_price)
        price_change = outcome.get("price_change_pct", 0)

        # Determine if the decision was correct
        was_correct = self._was_decision_correct(action, price_change)

        # Evaluate individual agents
        agent_evals = {}
        try:
            agent_recs = decision.get("agent_recommendations", {})
            if isinstance(agent_recs, str):
                agent_recs = json.loads(agent_recs)
        except:
            agent_recs = {}

        for agent_name, rec in agent_recs.items():
            if isinstance(rec, str):
                try:
                    rec = json.loads(rec)
                except:
                    continue
            agent_action = rec.get("action", "HOLD")
            agent_evals[agent_name] = {
                "recommended": agent_action,
                "was_correct": self._was_decision_correct(agent_action, price_change),
                "confidence": rec.get("confidence", 0),
            }

        feedback = {
            "decision_id": decision["id"],
            "ticker": ticker,
            "action": action,
            "entry_price": entry_price,
            "outcome_price": current_price,
            "price_change_pct": price_change,
            "was_correct": was_correct,
            "outcome_label": outcome.get("outcome_label", "UNKNOWN"),
            "max_favorable": outcome.get("max_favorable_pct", 0),
            "max_adverse": outcome.get("max_adverse_pct", 0),
            "agent_evaluations": agent_evals,
            "timestamp": datetime.now().isoformat(),
        }

        return feedback

    def _was_decision_correct(self, action: str, price_change_pct: float) -> bool:
        """
        Determine if a decision was correct based on action and subsequent price movement.
        """
        if action == "BUY":
            return price_change_pct > 0.5  # Made money on buy
        elif action == "SELL":
            return price_change_pct < -0.5  # Saved money by selling
        else:  # HOLD
            return abs(price_change_pct) < 3.0  # Hold was right if no big move

    def generate_llm_review(self, feedback: Dict) -> str:
        """
        Use LLM to generate a detailed review of why a decision was right or wrong.
        This review becomes learning context for future decisions.
        """
        if not self.client:
            return f"Decision was {'correct' if feedback['was_correct'] else 'incorrect'}. " \
                   f"Price moved {feedback['price_change_pct']:.2f}% after {feedback['action']}."

        prompt = f"""You are reviewing a past trading decision to learn from it.

DECISION MADE:
- Ticker: {feedback['ticker']}
- Action: {feedback['action']}
- Entry Price: ${feedback['entry_price']:.2f}
- Outcome Price: ${feedback['outcome_price']:.2f}
- Price Change: {feedback['price_change_pct']:.2f}%
- Was Correct: {'Yes' if feedback['was_correct'] else 'No'}

INDIVIDUAL AGENT RECOMMENDATIONS:
{json.dumps(feedback.get('agent_evaluations', {}), indent=2)}

Provide a concise review (2-3 paragraphs) answering:
1. What went RIGHT or WRONG with this decision?
2. Which agents were correct/incorrect and why?
3. What should we LEARN from this for future decisions?

Keep the review concise and actionable."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a senior trading performance reviewer."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error generating LLM review: {e}")
            return f"Review unavailable. Decision was {'correct' if feedback['was_correct'] else 'incorrect'}."

    def get_learning_context_for_ticker(self, ticker: str, limit: int = 5) -> str:
        """
        Get summarized learning context for a specific ticker.
        This is fed to agents when making new decisions.
        """
        decisions = self.journal.get_recent_decisions(limit=limit, ticker=ticker)
        if not decisions:
            return "No historical decisions for this ticker."

        context_parts = []
        for d in decisions[-limit:]:
            outcome = f"{d.get('price_change_pct', 'N/A')}%" if d.get('price_change_pct') else "pending"
            correct = "✓" if d.get('outcome_label') == "PROFITABLE" else "✗" if d.get('outcome_label') == "UNPROFITABLE" else "—"
            context_parts.append(
                f"[{d['timestamp'][:16]}] {d['action']} @ ${d['price']:.2f} → {outcome} {correct}"
            )

        return "\n".join(context_parts)
