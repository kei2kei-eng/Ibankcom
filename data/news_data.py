"""
News Data Fetcher & Sentiment Analyzer
======================================
Fetches news from multiple sources and analyzes sentiment.
"""

import requests
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class NewsArticle:
    """Represents a single news article."""
    title: str
    source: str
    published_at: str
    url: str
    summary: str = ""
    sentiment_score: float = 0.0  # -1 to 1
    relevance_score: float = 0.0  # 0 to 1
    impact_tags: List[str] = field(default_factory=list)


class NewsDataFetcher:
    """Fetches and analyzes news for stock trading decisions."""

    def __init__(self, openai_client=None):
        self.openai_client = openai_client
        self._news_cache: Dict[str, List[NewsArticle]] = {}
        self._cache_time: Dict[str, datetime] = {}
        self.cache_duration = timedelta(minutes=30)

    def _is_cache_valid(self, ticker: str) -> bool:
        if ticker not in self._news_cache:
            return False
        if ticker not in self._cache_time:
            return False
        return datetime.now() - self._cache_time[ticker] < self.cache_duration

    def fetch_news_yfinance(self, ticker: str) -> List[NewsArticle]:
        """Fetch news using yfinance (no API key needed)."""
        import yfinance as yf

        articles = []
        try:
            stock = yf.Ticker(ticker)
            news_items = stock.news or []

            for item in news_items[:15]:
                article = NewsArticle(
                    title=item.get("title", ""),
                    source=item.get("publisher", "Unknown"),
                    published_at=datetime.fromtimestamp(
                        item.get("providerPublishTime", 0)
                    ).strftime("%Y-%m-%d %H:%M") if item.get("providerPublishTime") else "Unknown",
                    url=item.get("link", ""),
                    summary=item.get("title", ""),  # yfinance often only has title
                )
                if article.title:
                    articles.append(article)

        except Exception as e:
            logger.error(f"Error fetching yfinance news for {ticker}: {e}")

        return articles

    def fetch_news_google(self, ticker: str, company_name: str = "") -> List[NewsArticle]:
        """Fetch news via Google News RSS (no API key needed)."""
        articles = []
        query = f"{ticker}+stock+{company_name}" if company_name else f"{ticker}+stock"
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

        try:
            import xml.etree.ElementTree as ET
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                root = ET.fromstring(response.content)
                items = root.findall(".//item")[:15]

                for item in items:
                    title = item.find("title")
                    link = item.find("link")
                    pub_date = item.find("pubDate")
                    source_elem = item.find("source")

                    article = NewsArticle(
                        title=title.text if title is not None else "",
                        source=source_elem.text if source_elem is not None else "Google News",
                        published_at=pub_date.text if pub_date is not None else "Unknown",
                        url=link.text if link is not None else "",
                    )
                    if article.title:
                        articles.append(article)

        except Exception as e:
            logger.error(f"Error fetching Google News for {ticker}: {e}")

        return articles

    def analyze_sentiment_with_llm(self, articles: List[NewsArticle], ticker: str) -> Dict:
        """
        Use LLM to analyze news sentiment and assess impact on stock.
        This is the core AI-powered news analysis.
        """
        if not self.openai_client or not articles:
            return {
                "overall_sentiment": 0.0,
                "sentiment_label": "NEUTRAL",
                "key_themes": [],
                "impact_assessment": "No news data available",
                "articles_analyzed": 0,
            }

        articles_text = "\n".join([
            f"[{i+1}] ({a.published_at}) {a.title} — Source: {a.source}"
            for i, a in enumerate(articles[:20])
        ])

        prompt = f"""You are a senior financial news analyst at a major investment bank.
Analyze the following recent news articles about {ticker} stock and provide your assessment.

RECENT NEWS ARTICLES:
{articles_text}

Please provide a JSON analysis with the following structure:
{{
    "overall_sentiment": <float from -1.0 to 1.0, where -1 is very bearish and 1 is very bullish>,
    "sentiment_label": "<VERY_BEARISH|BEARISH|NEUTRAL|BULLISH|VERY_BULLISH>",
    "confidence": <float from 0.0 to 1.0>,
    "key_themes": [<list of 3-5 key themes/topics>],
    "impact_assessment": "<2-3 sentence summary of how these news will likely affect {ticker}>",
    "short_term_impact": "<POSITIVE|NEGATIVE|NEUTRAL> with brief explanation",
    "catalysts": [<list of any specific catalysts mentioned>],
    "risks": [<list of risk factors identified>],
    "sector_implications": "<brief note on sector-wide impact>",
    "individual_article_scores": [
        {{"index": 1, "sentiment": 0.5, "impact_level": "HIGH|MEDIUM|LOW", "reasoning": "brief explanation"}}
    ]
}}

Be objective and analytical. Consider market efficiency — not all news moves stock prices.
Respond ONLY with valid JSON."""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a senior financial news analyst. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000,
            )

            result_text = response.choices[0].message.content.strip()
            # Clean up response
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]

            analysis = json.loads(result_text)
            analysis["articles_analyzed"] = len(articles)
            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in sentiment analysis: {e}")
            return {
                "overall_sentiment": 0.0,
                "sentiment_label": "NEUTRAL",
                "articles_analyzed": len(articles),
                "key_themes": [],
                "impact_assessment": "Failed to analyze news",
            }
        except Exception as e:
            logger.error(f"Error in LLM sentiment analysis: {e}")
            return {
                "overall_sentiment": 0.0,
                "sentiment_label": "NEUTRAL",
                "articles_analyzed": len(articles),
                "key_themes": [],
                "impact_assessment": f"Error: {str(e)}",
            }

    def get_news_analysis(self, ticker: str, company_name: str = "") -> Dict:
        """
        Main entry point: fetch news from multiple sources and analyze.
        """
        # Check cache
        if self._is_cache_valid(ticker):
            cached = self._news_cache[ticker]
            return self._analyze_cached(cached, ticker)

        # Fetch from multiple sources
        all_articles = []
        all_articles.extend(self.fetch_news_yfinance(ticker))
        all_articles.extend(self.fetch_news_google(ticker, company_name))

        # Deduplicate by title similarity
        seen_titles = set()
        unique_articles = []
        for article in all_articles:
            title_key = article.title.lower().strip()[:50]
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_articles.append(article)

        # Cache
        self._news_cache[ticker] = unique_articles
        self._cache_time[ticker] = datetime.now()

        # Analyze with LLM
        analysis = self.analyze_sentiment_with_llm(unique_articles, ticker)

        return analysis

    def _analyze_cached(self, articles: List[NewsArticle], ticker: str) -> Dict:
        """Re-analyze cached articles."""
        return self.analyze_sentiment_with_llm(articles, ticker)

    def generate_news_summary(self, ticker: str, company_name: str = "") -> str:
        """Generate a human-readable news summary for LLM consumption."""
        analysis = self.get_news_analysis(ticker, company_name)

        summary = f"""
=== News Analysis for {ticker} ===

Overall Sentiment: {analysis.get('sentiment_label', 'N/A')} ({analysis.get('overall_sentiment', 0):.2f})
Confidence: {analysis.get('confidence', 0):.2f}
Articles Analyzed: {analysis.get('articles_analyzed', 0)}

Key Themes: {', '.join(analysis.get('key_themes', []))}
Impact Assessment: {analysis.get('impact_assessment', 'N/A')}
Short-term Impact: {analysis.get('short_term_impact', 'N/A')}

Catalysts: {', '.join(analysis.get('catalysts', ['None identified']))}
Risks: {', '.join(analysis.get('risks', ['None identified']))}
Sector Implications: {analysis.get('sector_implications', 'N/A')}
"""
        return summary
