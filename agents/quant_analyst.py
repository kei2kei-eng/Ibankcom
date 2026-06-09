"""
Quantitative Analyst Agent
==========================
Uses quantitative models and statistical analysis.
Role: Quant Analyst at the iBank.
"""

import json
import logging
import numpy as np
from typing import Dict
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class QuantAnalystAgent(BaseAgent):
    """
    Quantitative Analyst — uses statistical models, mean reversion,
    momentum factors, and factor analysis.
    """

    def __init__(self, openai_client=None, model: str = "gpt-4o"):
        super().__init__(
            name="Quant Analyst",
            role="Senior Quantitative Analyst",
            openai_client=openai_client,
            model=model,
        )
        self.parameters = {
            "momentum_factor_weight": 0.30,
            "mean_reversion_weight": 0.25,
            "value_factor_weight": 0.20,
            "quality_factor_weight": 0.15,
            "volatility_factor_weight": 0.10,
            "lookback_period": 60,
            "z_score_threshold": 1.5,
        }

    def get_system_prompt(self) -> str:
        return f"""You are the Senior Quantitative Analyst at a prestigious investment bank.
Your expertise is in quantitative models, statistical analysis, and factor investing.

Your learnable parameters:
{json.dumps(self.parameters, indent=2)}

Your current accuracy: {self.accuracy:.1%} over {self.decisions_made} decisions.

ANALYSIS FRAMEWORK:
1. Factor Analysis: Momentum, Value, Quality, Low Volatility factors
2. Statistical Models: Z-scores, mean reversion signals
3. Risk-Adjusted Returns: Sharpe ratio, Sortino ratio considerations
4. Correlation Analysis: How this stock moves with the market
5. Quantitative Scoring: Multi-factor model output

KEY MODELS YOU CONSIDER:
- Momentum Score: Price momentum over various timeframes
- Mean Reversion: Distance from moving averages and historical norms
- Value Score: P/E, PEG, Price-to-Book relative to sector
- Quality Score: Profit margins, earnings stability
- Volatility Score: Risk-adjusted attractiveness

Respond ONLY with valid JSON:
{{
    "action": "BUY|SELL|HOLD",
    "confidence": <0.0-1.0>,
    "reasoning": "<detailed quantitative analysis>",
    "target_price": <float or null>,
    "stop_loss": <float or null>,
    "risk_level": "LOW|MEDIUM|HIGH",
    "quant_score": <-1.0 to 1.0>,
    "key_factors": ["<top quantitative factors>"],
    "details": {{
        "momentum_score": <-1.0 to 1.0>,
        "mean_reversion_score": <-1.0 to 1.0>,
        "value_score": <-1.0 to 1.0>,
        "quality_score": <-1.0 to 1.0>,
        "volatility_score": <-1.0 to 1.0>,
        "composite_score": <-1.0 to 1.0>,
        "expected_return": <float>,
        "sharpe_estimate": <float>
    }}
}}"""

    def analyze(self, ticker: str, market_data: Dict, news_data: Dict, portfolio: Dict, learning_context: str = "") -> Dict:
        """Perform quantitative analysis."""
        indicators = market_data.get("indicators", {})
        company_info = market_data.get("company_info", {})

        # Calculate quantitative factors locally
        local_quant = self._calculate_local_factors(indicators, company_info)

        prompt = f"""Analyze {ticker} ({company_info.get('company_name', ticker)}) from a QUANTITATIVE perspective.

MARKET DATA:
Price: ${indicators.get('current_price', 0):.2f}
P/E Ratio: {company_info.get('pe_ratio', 'N/A')}
Forward P/E: {company_info.get('forward_pe', 'N/A')}
PEG Ratio: {company_info.get('peg_ratio', 'N/A')}
Beta: {company_info.get('beta', 'N/A')}
Profit Margin: {company_info.get('profit_margin', 'N/A')}
Revenue Growth: {company_info.get('revenue_growth', 'N/A')}
Dividend Yield: {company_info.get('dividend_yield', 0)}
Analyst Target Price: ${company_info.get('target_price', 'N/A')}

LOCAL QUANT CALCULATIONS:
Price vs SMA20 Z-Score: {local_quant.get('price_sma20_zscore', 0):.2f}
Price vs SMA50 Z-Score: {local_quant.get('price_sma50_zscore', 0):.2f}
RSI Z-Score: {local_quant.get('rsi_zscore', 0):.2f}
Momentum (20d): {local_quant.get('momentum_20d', 0):.2f}%
Momentum (60d): {local_quant.get('momentum_60d', 0):.2f}%
Volatility Percentile: {local_quant.get('vol_percentile', 0):.1f}%
Volume Ratio: {local_quant.get('volume_ratio', 0):.2f}

CURRENT PORTFOLIO POSITION: {portfolio.get('holdings', {}).get(ticker, 'No position')}

{f"LEARNING CONTEXT - Review your past performance: {learning_context}" if learning_context else ""}

Apply your multi-factor quantitative model and provide analysis as JSON."""

        response = self.query_llm(prompt)
        result = self.parse_json_response(response)
        result["agent"] = self.name
        result["agent_type"] = "quant_analyst"
        result["local_quant"] = local_quant
        return result

    def _calculate_local_factors(self, indicators: Dict, company_info: Dict) -> Dict:
        """Calculate quantitative factors locally (no LLM needed for math)."""
        current_price = indicators.get("current_price", 0)
        results = {}

        try:
            # Z-scores
            sma_20 = indicators.get("sma_20", current_price)
            sma_50 = indicators.get("sma_50", current_price)
            atr = indicators.get("atr", max(0.01, current_price * 0.02))

            results["price_sma20_zscore"] = (current_price - sma_20) / atr if atr > 0 else 0
            results["price_sma50_zscore"] = (current_price - sma_50) / atr if atr > 0 else 0

            # RSI normalization
            rsi = indicators.get("rsi", 50)
            results["rsi_zscore"] = (rsi - 50) / 20

            # Momentum
            results["momentum_20d"] = indicators.get("daily_change_pct", 0) * 20  # rough estimate
            results["momentum_60d"] = (
                (current_price / indicators.get("sma_50", current_price) - 1) * 100
                if indicators.get("sma_50", 0) > 0 else 0
            )

            # Volume ratio
            vol_sma = indicators.get("volume_sma", 1)
            current_vol = indicators.get("current_volume", 0)
            results["volume_ratio"] = current_vol / vol_sma if vol_sma > 0 else 1.0

            # Volatility percentile (rough)
            vol = indicators.get("volatility_30d", 0)
            results["vol_percentile"] = min(vol / 0.60 * 100, 100)

        except Exception as e:
            logger.error(f"Error in local quant calculations: {e}")

        return results
