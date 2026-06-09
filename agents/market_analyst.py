"""
Market Analyst Agent
====================
Analyzes technical indicators and market trends.
Role: Senior Technical Analyst at the iBank.
"""

import json
import logging
from typing import Dict
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class MarketAnalystAgent(BaseAgent):
    """
    Senior Technical Analyst — reads charts, patterns, and technical indicators.
    Provides BUY/SELL/HOLD recommendations based on technical analysis.
    """

    def __init__(self, openai_client=None, model: str = "gpt-4o"):
        super().__init__(
            name="Market Analyst",
            role="Senior Technical Analyst",
            openai_client=openai_client,
            model=model,
        )
        self.parameters = {
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "sma_crossover_weight": 0.3,
            "macd_weight": 0.25,
            "volume_weight": 0.2,
            "support_resistance_weight": 0.25,
        }

    def get_system_prompt(self) -> str:
        return f"""You are the Senior Technical Market Analyst at a prestigious investment bank.
Your expertise is in technical analysis, chart patterns, and market trends.

Your learnable parameters (which may be adjusted by the learning system):
{json.dumps(self.parameters, indent=2)}

Your current accuracy: {self.accuracy:.1%} over {self.decisions_made} decisions.

ANALYSIS FRAMEWORK:
1. Trend Analysis: SMA/EMA crossovers, MACD direction
2. Momentum: RSI, Stochastic oscillator readings
3. Volatility: Bollinger Bands, ATR
4. Volume Analysis: Volume trends, OBV
5. Support/Resistance: Key price levels

RESPONSIBLE TRADING PRINCIPLES:
- Never recommend more than 10% of portfolio in a single position
- Consider stop-loss levels for every recommendation
- Factor in market liquidity
- Be cautious around major support/resistance levels

Respond ONLY with valid JSON in this exact format:
{{
    "action": "BUY|SELL|HOLD",
    "confidence": <0.0-1.0>,
    "reasoning": "<detailed technical analysis reasoning>",
    "target_price": <float or null>,
    "stop_loss": <float or null>,
    "risk_level": "LOW|MEDIUM|HIGH",
    "trend": "BULLISH|BEARISH|NEUTRAL",
    "key_signals": ["<list of key technical signals>"],
    "timeframe": "<short-term / medium-term / long-term outlook>",
    "details": {{
        "trend_score": <-1.0 to 1.0>,
        "momentum_score": <-1.0 to 1.0>,
        "volume_score": <-1.0 to 1.0>,
        "overall_technical_score": <-1.0 to 1.0>
    }}
}}"""

    def analyze(self, ticker: str, market_data: Dict, news_data: Dict, portfolio: Dict, learning_context: str = "") -> Dict:
        """Perform technical analysis."""
        indicators = market_data.get("indicators", {})
        company_info = market_data.get("company_info", {})

        prompt = f"""Analyze {ticker} ({company_info.get('company_name', ticker)}) from a TECHNICAL perspective.

CURRENT MARKET DATA:
Price: ${indicators.get('current_price', 0):.2f}
Daily Change: {indicators.get('daily_change_pct', 0):.2f}%
RSI (14): {indicators.get('rsi', 0):.1f}
MACD: {indicators.get('macd', 0):.4f} / Signal: {indicators.get('macd_signal', 0):.4f}
SMA 20/50/200: ${indicators.get('sma_20', 0):.2f} / ${indicators.get('sma_50', 0):.2f} / ${indicators.get('sma_200', 0):.2f}
Bollinger Bands: ${indicators.get('bb_upper', 0):.2f} - ${indicators.get('bb_lower', 0):.2f}
ATR: {indicators.get('atr', 0):.4f}
Stochastic %K/%D: {indicators.get('stoch_k', 0):.1f} / {indicators.get('stoch_d', 0):.1f}
Volume: {indicators.get('current_volume', 0):,.0f} (Avg: {indicators.get('volume_sma', 0):,.0f})
Volatility (30d): {indicators.get('volatility_30d', 0):.4f}
Support: ${indicators.get('support', 0):.2f} / Resistance: ${indicators.get('resistance', 0):.2f}
52W High: ${company_info.get('52w_high', 0):.2f} / 52W Low: ${company_info.get('52w_low', 0):.2f}

CURRENT PORTFOLIO POSITION: {portfolio.get('holdings', {}).get(ticker, 'No position')}

{f"LEARNING CONTEXT - Review your past performance: {learning_context}" if learning_context else ""}

Provide your technical analysis as JSON."""

        response = self.query_llm(prompt)
        result = self.parse_json_response(response)
        result["agent"] = self.name
        result["agent_type"] = "market_analyst"
        return result
