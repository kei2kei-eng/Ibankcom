"""
Adaptive Logic Engine
=====================
The core auto-learning mechanism that adjusts agent parameters
based on review feedback.
"""

import json
import logging
from typing import Dict, List
from datetime import datetime
from .decision_journal import DecisionJournal

logger = logging.getLogger(__name__)


class AdaptiveLogicEngine:
    """
    Adjusts agent parameters, weights, and decision logic
    based on performance feedback. This is how the system LEARNS.
    
    Learning mechanisms:
    1. Weight Adjustment: Agents that perform well get more influence
    2. Parameter Tuning: Agent-specific parameters are adjusted
    3. Threshold Adjustment: Confidence thresholds are calibrated
    4. Strategy Selection: Different strategies are tried based on market regime
    """

    def __init__(self, journal: DecisionJournal, openai_client=None, model: str = "gpt-4o"):
        self.journal = journal
        self.client = openai_client
        self.model = model
        self.learning_rate = 0.1

    def learn_from_feedback(self, feedback_list: List[Dict], agents: Dict):
        """
        Main learning loop: process feedback and adjust all agents.
        
        Args:
            feedback_list: List of feedback dicts from DecisionReviewer
            agents: Dict of agent_name -> agent_instance
        """
        if not feedback_list:
            logger.info("No feedback to learn from.")
            return

        for feedback in feedback_list:
            self._process_single_feedback(feedback, agents)

        # Generate summary
        summary = self._generate_learning_summary(feedback_list)
        logger.info(f"Learning session complete: {summary}")
        return summary

    def _process_single_feedback(self, feedback: Dict, agents: Dict):
        """Process one piece of feedback and update relevant agents."""
        agent_evals = feedback.get("agent_evaluations", {})

        for agent_name, eval_data in agent_evals.items():
            # Find matching agent
            agent = self._find_agent(agents, agent_name)
            if not agent:
                continue

            was_correct = eval_data.get("was_correct", False)
            confidence = eval_data.get("confidence", 0.5)

            # 1. Update agent's performance tracking
            agent.update_performance(was_correct)

            # 2. Adjust agent's weight based on accuracy
            old_weight = agent.weight
            if was_correct:
                # Increase weight slightly
                adjustment = self.learning_rate * confidence
                agent.weight = min(agent.weight + adjustment, 2.0)
            else:
                # Decrease weight, more if confident but wrong
                adjustment = self.learning_rate * confidence * 1.5
                agent.weight = max(agent.weight - adjustment, 0.2)

            # 3. Record the adjustment
            self.journal.record_learning_adjustment(
                adjustment_type="weight",
                agent_name=agent.name,
                parameter_name="weight",
                old_value=str(old_weight),
                new_value=str(agent.weight),
                reason=f"{'Correct' if was_correct else 'Incorrect'} prediction (confidence: {confidence:.2f})",
                performance_data={
                    "was_correct": was_correct,
                    "accuracy": agent.accuracy,
                    "confidence": confidence,
                },
            )

            # 4. Record agent performance
            self.journal.record_agent_performance(
                agent_name=agent.name,
                agent_type=agent.name.lower().replace(" ", "_"),
                ticker=feedback["ticker"],
                recommended_action=eval_data.get("recommended", "HOLD"),
                confidence=confidence,
                was_correct=was_correct,
                accuracy_running=agent.accuracy,
                weight=agent.weight,
                parameters=agent.parameters,
            )

            # 5. Adjust agent-specific parameters
            self._adjust_agent_parameters(agent, feedback, was_correct, confidence)

    def _adjust_agent_parameters(self, agent, feedback: Dict, was_correct: bool, confidence: float):
        """
        Adjust agent-specific learnable parameters.
        Uses a simple gradient-like approach.
        """
        price_change = feedback.get("price_change_pct", 0)

        # Get agent-specific parameter adjustments
        adjustments = self._compute_parameter_adjustments(
            agent, feedback, was_correct, confidence, price_change
        )

        for param_name, (old_val, new_val, reason) in adjustments.items():
            if param_name in agent.parameters:
                agent.parameters[param_name] = new_val
                self.journal.record_learning_adjustment(
                    adjustment_type="parameter",
                    agent_name=agent.name,
                    parameter_name=param_name,
                    old_value=str(old_val),
                    new_value=str(new_val),
                    reason=reason,
                )

    def _compute_parameter_adjustments(self, agent, feedback, was_correct, confidence, price_change):
        """
        Compute parameter adjustments based on agent type and feedback.
        This is where the real learning intelligence lives.
        """
        adjustments = {}
        lr = self.learning_rate

        # Market Analyst parameter adjustments
        if "market" in agent.name.lower():
            params = agent.parameters
            if "rsi_overbought" in params and not was_correct and feedback["action"] == "BUY":
                # Bought at overbought? Increase threshold
                old = params["rsi_overbought"]
                new = min(old + lr * 5, 85)
                adjustments["rsi_overbought"] = (old, new, "Adjusting RSI overbought threshold after failed BUY")
            if "rsi_oversold" in params and not was_correct and feedback["action"] == "SELL":
                old = params["rsi_oversold"]
                new = max(old - lr * 5, 15)
                adjustments["rsi_oversold"] = (old, new, "Adjusting RSI oversold threshold after failed SELL")

        # News Analyst parameter adjustments
        elif "news" in agent.name.lower():
            params = agent.parameters
            if "sentiment_weight" in params:
                # If news analysis was wrong, adjust sentiment weight
                old = params["sentiment_weight"]
                if was_correct:
                    new = min(old + lr * 0.05, 0.6)
                else:
                    new = max(old - lr * 0.05, 0.2)
                adjustments["sentiment_weight"] = (old, new, "Adjusting sentiment weight based on accuracy")

        # Quant Analyst parameter adjustments
        elif "quant" in agent.name.lower():
            params = agent.parameters
            if "z_score_threshold" in params:
                old = params["z_score_threshold"]
                if was_correct:
                    # Correct — can be slightly more aggressive
                    new = max(old - lr * 0.1, 1.0)
                else:
                    # Wrong — be more conservative
                    new = min(old + lr * 0.1, 2.5)
                adjustments["z_score_threshold"] = (old, new, "Adjusting Z-score threshold based on accuracy")

        # Risk Manager parameter adjustments
        elif "risk" in agent.name.lower():
            params = agent.parameters
            if was_correct and feedback["action"] != "HOLD":
                # Approved a good trade — can relax slightly
                if "max_single_position_pct" in params:
                    old = params["max_single_position_pct"]
                    new = min(old + lr * 0.005, 0.15)
                    adjustments["max_single_position_pct"] = (old, new, "Relaxing position limit after correct approval")
            elif not was_correct:
                # Approved a bad trade — tighten
                if "max_single_position_pct" in params:
                    old = params["max_single_position_pct"]
                    new = max(old - lr * 0.005, 0.05)
                    adjustments["max_single_position_pct"] = (old, new, "Tightening position limit after incorrect approval")

        return adjustments

    def _find_agent(self, agents: Dict, agent_name: str):
        """Find an agent by name (fuzzy matching)."""
        name_lower = agent_name.lower().replace(" ", "_").replace("_", " ")

        for key, agent in agents.items():
            agent_name_lower = agent.name.lower()
            key_lower = key.lower()
            if (
                name_lower in agent_name_lower or
                agent_name_lower in name_lower or
                name_lower in key_lower or
                key_lower in name_lower
            ):
                return agent
        return None

    def _generate_learning_summary(self, feedback_list: List[Dict]) -> str:
        """Generate a summary of the learning session."""
        total = len(feedback_list)
        correct = sum(1 for f in feedback_list if f.get("was_correct"))

        agent_stats = {}
        for f in feedback_list:
            for agent_name, eval_data in f.get("agent_evaluations", {}).items():
                if agent_name not in agent_stats:
                    agent_stats[agent_name] = {"correct": 0, "total": 0}
                agent_stats[agent_name]["total"] += 1
                if eval_data.get("was_correct"):
                    agent_stats[agent_name]["correct"] += 1

        summary = f"Reviewed {total} decisions ({correct}/{total} correct).\n"
        for name, stats in agent_stats.items():
            pct = stats["correct"] / max(stats["total"], 1) * 100
            summary += f"  {name}: {stats['correct']}/{stats['total']} ({pct:.0f}%)\n"

        return summary

    def generate_agent_learning_prompt(self, agent_name: str, feedback_list: List[Dict]) -> str:
        """
        Generate a learning context prompt for a specific agent.
        This is injected into the agent's analysis prompt.
        """
        relevant_feedback = []
        for f in feedback_list:
            for aname, aeval in f.get("agent_evaluations", {}).items():
                if agent_name.lower().replace(" ", "_") in aname.lower().replace(" ", "_"):
                    relevant_feedback.append({
                        "ticker": f["ticker"],
                        "action": aeval.get("recommended"),
                        "was_correct": aeval.get("was_correct"),
                        "actual_change": f.get("price_change_pct"),
                    })

        if not relevant_feedback:
            return ""

        recent = relevant_feedback[-5:]
        correct = sum(1 for r in recent if r["was_correct"])
        total = len(recent)

        prompt = f"""
=== LEARNING FEEDBACK ===
Your recent accuracy: {correct}/{total} ({correct/total*100:.0f}%)
Recent decisions: {json.dumps(recent, indent=2)}

Please consider these past results when making your current recommendation.
Learn from both your successes and mistakes.
"""
        return prompt

    def get_current_weights(self, agents: Dict) -> Dict[str, float]:
        """Get current agent weights, normalized."""
        weights = {}
        total = 0
        for key, agent in agents.items():
            weights[key] = agent.weight
            total += agent.weight

        # Normalize
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights
