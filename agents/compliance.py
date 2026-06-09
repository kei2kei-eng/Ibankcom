"""
Compliance Officer Agent
========================
Ensures all trades comply with regulations and internal policies.
Role: Compliance Officer at the iBank.
"""

import json
import logging
from typing import Dict
from datetime import datetime
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ComplianceOfficerAgent(BaseAgent):
    """
    Compliance Officer — ensures trades comply with regulations,
    internal policies, and ethical guidelines.
    """

    def __init__(self, openai_client=None, model: str = "gpt-4o"):
        super().__init__(
            name="Compliance Officer",
            role="Chief Compliance Officer",
            openai_client=openai_client,
            model=model,
        )
        self.parameters = {
            "max_daily_trades": 20,
            "max_single_trade_value": 100_000,
            "restricted_periods": ["pre_market", "after_hours"],
            "min_time_between_trades_min": 5,
        }

    def get_system_prompt(self) -> str:
        return f"""You are the Chief Compliance Officer at a prestigious investment bank.
Your role is to ensure all trading activities comply with regulations and internal policies.

COMPLIANCE RULES:
{json.dumps(self.parameters, indent=2)}

COMPLIANCE CHECKS:
1. Trade size limits
2. Trading frequency limits
3. Restricted stock checks
4. Market manipulation prevention
5. Fiduciary duty verification
6. Risk disclosure completeness

You have VETO power over any trade that violates compliance rules.

Respond ONLY with valid JSON:
{{
    "approved": <true/false>,
    "confidence": <0.0-1.0>,
    "reasoning": "<compliance assessment>",
    "warnings": ["<list of compliance warnings>"],
    "required_disclosures": ["<list of required disclosures>"],
    "details": {{
        "trade_size_compliant": <true/false>,
        "frequency_compliant": <true/false>,
        "restrictions_clear": <true/false>,
        "overall_compliance": "<COMPLIANT|REVIEW_REQUIRED|NON_COMPLIANT>"
    }}
}}"""

    def analyze(self, ticker: str, market_data: Dict, news_data: Dict, portfolio: Dict, learning_context: str = "") -> Dict:
        """Perform compliance check."""
        indicators = market_data.get("indicators", {})
        holdings = portfolio.get("holdings", {})

        prompt = f"""Perform a COMPLIANCE CHECK for a potential trade on {ticker}.

Trade Context:
- Current Price: ${indicators.get('current_price', 0):.2f}
- Portfolio Total: ${portfolio.get('total_value', 0):,.2f}
- Cash Available: ${portfolio.get('cash', 0):,.2f}
- Current Positions: {len(holdings)}
- Current Exposure: {portfolio.get('exposure_pct', 0):.1f}%

Check all compliance rules and determine if the trade can proceed.
Provide your compliance assessment as JSON."""

        response = self.query_llm(prompt)
        result = self.parse_json_response(response)
        result["agent"] = self.name
        result["agent_type"] = "compliance"
        return result
