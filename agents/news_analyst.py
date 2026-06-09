"""
News Analyst Agent
==================
Analyzes news sentiment and assesses impact on stocks.
Role: Senior News Analyst at the iBank.
"""

import json
import logging
from typing import Dict
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class NewsAnalystAgent(BaseAgent):
    """
    Senior News Analyst — reads and interprets financial news,
    earnings reports, SEC filings, and global events.
    """

    def __init__(self, openai_client=None, model: str = "gpt-4o"):
        super().__init__(
            name="News Analyst",
            role="Senior News & Events Analyst",
            openai_client=openai_client,
            model=model,
        )
        self.parameters = {
            "sentiment_weight": 0.4,
            "catalyst_weight": 0.3,
            "sector_impact_weight": 0.15,
            "macro_impact_weight": 0.15,
            "negative_threshold": -0.3,
            "positive_threshold": 0.3,
        }

    def get_system_prompt(self) -> str:
        return f"""You are the Senior News & Events Analyst at a prestigious investment bank.
Your expertise is in news analysis, event-driven trading, and understanding how
information flows affect stock prices.

Your learnable parameters:
{json.dumps(self.parameters, indent=2)}

Your current accuracy: {self.accuracy:.1%} over {self.decisions_made} decisions.

ANALYSIS FRAMEWORK:
1. News Sentiment: Overall bullish/bearish tone of recent news
2. Catalyst Identification: Earnings, FDA approvals, M&A, product launches
3. Impact Duration: Short-term noise vs structural change
4. Market Expectations: Is news already priced in?
5. Sector Implications: Does this news affect the broader sector?
6. Risk Assessment: What could go wrong?

KEY PRINCIPLES:
- "Buy the rumor, sell the news" — consider if news is already priced in
- Distinguish between noise and signal
- Consider second-order effects
- Pay attention to SEC filings and insider activity

Respond ONLY with valid JSON:
{{
    "action": "BUY|SELL|HOLD",
    "confidence": <0.0-1.0>,
    "reasoning": "<detailed news analysis>",
    "target_price": <float or null>,
    "stop_loss": <float or null>,
    "risk_level": "LOW|MEDIUM|HIGH",
    "sentiment": <float -1.0 to 1.0>,
    "key_news": ["<top 3-5 impactful news items>"],
    "catalysts": ["<identified catalysts>"],
    "risks": ["<identified risk factors>"],
    "is_priced_in": <true/false>,
    "details": {{
        "news_sentiment_score": <-1.0 to 1.0>,
        "catalyst_strength": <0.0 to 1.0>,
        "information_quality": <0.0 to 1.0>,
        "market_surprise_factor": <-1.0 to 1.0>
    }}
}}"""

    def analyze(self, ticker: str, market_data: Dict, news_data: Dict, portfolio: Dict, learning_context: str = "") -> Dict:
        """Perform news-based analysis."""
        news_analysis = news_data.get("analysis", {})
        company_info = market_data.get("company_info", {})

        prompt = f"""Analyze {ticker} ({company_info.get('company_name', ticker)}) from a NEWS & EVENTS perspective.

NEWS ANALYSIS RESULTS:
Sentiment: {news_analysis.get('sentiment_label', 'N/A')} (Score: {news_analysis.get('overall_sentiment', 0):.2f})
Confidence: {news_analysis.get('confidence', 0):.2f}
Articles Analyzed: {news_analysis.get('articles_analyzed', 0)}

Key Themes: {', '.join(news_analysis.get('key_themes', []))}
Impact Assessment: {news_analysis.get('impact_assessment', 'N/A')}
Short-term Impact: {news_analysis.get('short_term_impact', 'N/A')}

Catalysts: {', '.join(news_analysis.get('catalysts', ['None']))}
Risks: {', '.join(news_analysis.get('risks', ['None']))}
Sector Implications: {news_analysis.get('sector_implications', 'N/A')}

CURRENT PRICE: ${market_data.get('indicators', {}).get('current_price', 0):.2f}
CURRENT PORTFOLIO POSITION: {portfolio.get('holdings', {}).get(ticker, 'No position')}

{f"LEARNING CONTEXT - Review your past performance: {learning_context}" if learning_context else ""}

Consider:
1. Is this news already priced into the stock?
2. What is the quality and reliability of the sources?
3. Are there upcoming catalysts (earnings, FDA decisions, product launches)?
4. What is the market's likely reaction?

Provide your news analysis as JSON."""

        response = self.query_llm(prompt)
        result = self.parse_json_response(response)
        result["agent"] = self.name
        result["agent_type"] = "news_analyst"
        return result
