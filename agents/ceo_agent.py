"""
CEO Agent (Decision Maker)
==========================
The final decision-maker who synthesizes all agent inputs.
Role: CEO / Chief Investment Officer of the iBank.
"""

import json
import logging
from typing import Dict, List
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class CEOAgent(BaseAgent):
    """
    CEO / Chief Investment Officer — receives recommendations from all agents
    and makes the final BUY/SELL/HOLD decision. Incorporates learning feedback.
    """

    def __init__(self, openai_client=None, model: str = "gpt-4o"):
        super().__init__(
            name="CEO",
            role="Chief Executive Officer & Investment Decision Maker",
            openai_client=openai_client,
            model=model,
        )
        self.parameters = {
            "min_confidence_to_trade": 0.65,
            "consensus_threshold": 0.6,
            "contrarian_factor": 0.1,
            "learning_weight": 0.15,
        }

    def get_system_prompt(self) -> str:
        return f"""You are the CEO and Chief Investment Officer of a prestigious AI-powered investment bank.
You receive recommendations from multiple specialist agents and make the FINAL trading decision.

Your learnable parameters:
{json.dumps(self.parameters, indent=2)}

Your current accuracy: {self.accuracy:.1%} over {self.decisions_made} decisions.

DECISION FRAMEWORK:
1. Synthesize all agent recommendations
2. Weight agents by their historical accuracy (provided)
3. Consider the confidence level of each recommendation
4. Apply risk management constraints
5. Factor in learning feedback from past decisions
6. Make a clear, actionable final decision

DECISION RULES:
- If overall confidence < {self.parameters['min_confidence_to_trade']}, recommend HOLD
- If Risk Manager says REJECT/EXTREME, strongly lean toward HOLD
- If Compliance says NON_COMPLIANT, the trade CANNOT proceed
- Consider consensus among agents — more agreement = higher confidence
- You have the final authority, but you must justify overrides

RESPONSIBILITY:
You are ultimately responsible for every trade. Be thoughtful, analytical,
and always protect the portfolio while seeking reasonable returns.

Respond ONLY with valid JSON:
{{
    "final_action": "BUY|SELL|HOLD",
    "confidence": <0.0-1.0>,
    "reasoning": "<comprehensive decision reasoning>",
    "position_size_pct": <0.0 to max_position_pct>,
    "target_price": <float or null>,
    "stop_loss": <float or null>,
    "take_profit": <float or null>,
    "risk_level": "LOW|MEDIUM|HIGH",
    "agent_consensus": "<UNANIMOUS|MAJORITY|DIVIDED|NO_CONSENSUS>",
    "override_reason": "<null or reason if overriding agent consensus>",
    "execution_notes": "<any special execution instructions>",
    "details": {{
        "weighted_bull_score": <float>,
        "weighted_bear_score": <float>,
        "consensus_strength": <0.0 to 1.0>,
        "risk_adjusted_score": <-1.0 to 1.0>,
        "learning_adjustment": <float>
    }}
}}"""

    def make_decision(
        self,
        ticker: str,
        agent_recommendations: Dict[str, Dict],
        market_data: Dict,
        portfolio: Dict,
        agent_weights: Dict[str, float],
        learning_context: str = "",
    ) -> Dict:
        """
        Synthesize all agent recommendations into a final decision.
        This is the main decision-making method.
        """
        # Build the synthesis prompt
        recommendations_text = ""
        for agent_name, rec in agent_recommendations.items():
            weight = agent_weights.get(agent_name.replace(" ", "_").lower(), 1.0)
            recommendations_text += f"""
--- {rec.get('agent', agent_name)} (Weight: {weight:.2f}) ---
Action: {rec.get('action', 'HOLD')}
Confidence: {rec.get('confidence', 0):.2f}
Risk Level: {rec.get('risk_level', 'N/A')}
Reasoning: {rec.get('reasoning', 'N/A')[:500]}
Details: {json.dumps(rec.get('details', {}), indent=2)}
"""

        indicators = market_data.get("indicators", {})
        company_info = market_data.get("company_info", {})

        prompt = f"""Make the FINAL investment decision for {ticker} ({company_info.get('company_name', ticker)}).

CURRENT MARKET STATE:
Price: ${indicators.get('current_price', 0):.2f}
Daily Change: {indicators.get('daily_change_pct', 0):.2f}%
Sector: {company_info.get('sector', 'Unknown')}

PORTFOLIO STATUS:
Total Value: ${portfolio.get('total_value', 0):,.2f}
Cash Available: ${portfolio.get('cash', 0):,.2f}
Current Exposure: {portfolio.get('exposure_pct', 0):.1f}%
Current Position: {portfolio.get('holdings', {}).get(ticker, 'No position')}

AGENT RECOMMENDATIONS:
{recommendations_text}

{f"LEARNING CONTEXT - Historical performance feedback: {learning_context}" if learning_context else ""}

SYNTHESIZE all agent inputs, apply your judgment, and make the FINAL decision.
Consider each agent's weight and accuracy when making your decision.
If agents disagree, explain your reasoning for the final choice.

Provide your final decision as JSON."""

        response = self.query_llm(prompt)
        result = self.parse_json_response(response)
        result["agent"] = self.name
        result["agent_type"] = "ceo"
        result["timestamp"] = self._get_timestamp()
        result["ticker"] = ticker
        result["agent_inputs"] = {
            name: {
                "action": rec.get("action"),
                "confidence": rec.get("confidence"),
            }
            for name, rec in agent_recommendations.items()
        }
        return result

    def analyze(self, ticker: str, market_data: Dict, news_data: Dict, portfolio: Dict, learning_context: str = "") -> Dict:
        """Standard analyze interface — delegates to make_decision."""
        return self.make_decision(
            ticker=ticker,
            agent_recommendations={},
            market_data=market_data,
            portfolio=portfolio,
            agent_weights={},
            learning_context=learning_context,
        )

    def _get_timestamp(self):
        from datetime import datetime
        return datetime.now().isoformat()
