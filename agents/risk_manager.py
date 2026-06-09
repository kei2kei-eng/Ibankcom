"""
Risk Manager Agent
==================
Evaluates risk and portfolio exposure.
Role: Chief Risk Officer at the iBank.
"""

import json
import logging
from typing import Dict
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class RiskManagerAgent(BaseAgent):
    """
    Chief Risk Officer — evaluates risk, sets position limits,
    and ensures portfolio is properly balanced.
    """

    def __init__(self, openai_client=None, model: str = "gpt-4o"):
        super().__init__(
            name="Risk Manager",
            role="Chief Risk Officer",
            openai_client=openai_client,
            model=model,
        )
        self.parameters = {
            "max_portfolio_volatility": 0.25,
            "max_single_position_pct": 0.10,
            "max_sector_exposure_pct": 0.30,
            "max_drawdown_tolerance": 0.15,
            "var_confidence_level": 0.95,
            "correlation_threshold": 0.70,
        }

    def get_system_prompt(self) -> str:
        return f"""You are the Chief Risk Officer at a prestigious investment bank.
Your primary responsibility is to protect capital and manage portfolio risk.

Your learnable parameters:
{json.dumps(self.parameters, indent=2)}

Your current accuracy: {self.accuracy:.1%} over {self.decisions_made} decisions.

RISK MANAGEMENT FRAMEWORK:
1. Position Sizing: Is the proposed position size appropriate?
2. Portfolio Exposure: Are we over-concentrated in any sector/stock?
3. Volatility Risk: Is the current volatility acceptable?
4. Correlation Risk: Are positions too correlated?
5. Drawdown Risk: What is the maximum potential loss?
6. Liquidity Risk: Can we exit positions quickly?
7. Market Regime: Are we in a bull, bear, or sideways market?

YOUR AUTHORITY:
- You can VETO any trade that exceeds risk limits
- You can recommend reducing existing positions
- You set stop-loss levels
- You determine maximum position sizes

Respond ONLY with valid JSON:
{{
    "action": "APPROVE|REJECT|REDUCE|HOLD",
    "confidence": <0.0-1.0>,
    "reasoning": "<detailed risk assessment>",
    "max_position_size": <float - maximum dollars to invest>,
    "stop_loss_price": <float>,
    "take_profit_price": <float>,
    "risk_level": "LOW|MEDIUM|HIGH|EXTREME",
    "portfolio_risk_score": <0.0 to 1.0>,
    "warnings": ["<list of risk warnings>"],
    "details": {{
        "position_risk": <0.0 to 1.0>,
        "portfolio_concentration_risk": <0.0 to 1.0>,
        "sector_exposure_risk": <0.0 to 1.0>,
        "overall_risk_assessment": "<SAFE|MODERATE|ELEVATED|DANGEROUS>"
    }}
}}"""

    def analyze(self, ticker: str, market_data: Dict, news_data: Dict, portfolio: Dict, learning_context: str = "") -> Dict:
        """Perform risk analysis."""
        indicators = market_data.get("indicators", {})
        company_info = market_data.get("company_info", {})

        # Calculate portfolio risk metrics
        portfolio_risk = self._calculate_portfolio_risk(portfolio, market_data)

        prompt = f"""Assess the RISK of trading {ticker} ({company_info.get('company_name', ticker)}).

STOCK RISK METRICS:
Current Price: ${indicators.get('current_price', 0):.2f}
Beta: {company_info.get('beta', 'N/A')}
30-Day Volatility: {indicators.get('volatility_30d', 0):.4f}
ATR: {indicators.get('atr', 0):.4f}
Avg Daily Volume: {company_info.get('avg_volume', 0):,.0f}
Short Ratio: {company_info.get('short_ratio', 'N/A')}

PORTFOLIO STATUS:
Total Value: ${portfolio.get('total_value', 0):,.2f}
Cash: ${portfolio.get('cash', 0):,.2f}
Invested: ${portfolio.get('invested', 0):,.2f}
Exposure: {portfolio.get('exposure_pct', 0):.1f}%
Number of Positions: {portfolio.get('num_positions', 0)}

PORTFOLIO RISK METRICS:
Concentration Risk: {portfolio_risk.get('concentration_risk', 0):.2f}
Sector Exposure: {json.dumps(portfolio_risk.get('sector_exposure', {}))}
Largest Position Pct: {portfolio_risk.get('largest_position_pct', 0):.1f}%

NEWS RISK:
{news_data.get('analysis', {}).get('sentiment_label', 'N/A')} sentiment with risks: {', '.join(news_data.get('analysis', {}).get('risks', ['None']))}

{f"LEARNING CONTEXT - Review your past performance: {learning_context}" if learning_context else ""}

Evaluate the risk of adding to or initiating a position in {ticker}.
If the trade is too risky, REJECT it. If position sizing needs adjustment, specify the maximum.
Provide your risk assessment as JSON."""

        response = self.query_llm(prompt)
        result = self.parse_json_response(response)
        result["agent"] = self.name
        result["agent_type"] = "risk_manager"
        result["portfolio_risk"] = portfolio_risk
        return result

    def _calculate_portfolio_risk(self, portfolio: Dict, market_data: Dict) -> Dict:
        """Calculate portfolio-level risk metrics."""
        holdings = portfolio.get("holdings", {})
        total_value = portfolio.get("total_value", 1)

        risk = {
            "concentration_risk": 0.0,
            "sector_exposure": {},
            "largest_position_pct": 0.0,
        }

        try:
            position_pcts = []
            for ticker, position in holdings.items():
                pct = position.get("value", 0) / total_value
                position_pcts.append(pct)
                sector = position.get("sector", "Unknown")
                risk["sector_exposure"][sector] = risk["sector_exposure"].get(sector, 0) + pct

            if position_pcts:
                # HHI (Herfindahl-Hirschman Index) for concentration
                risk["concentration_risk"] = sum(p ** 2 for p in position_pcts)
                risk["largest_position_pct"] = max(position_pcts) * 100

        except Exception as e:
            logger.error(f"Error calculating portfolio risk: {e}")

        return risk
