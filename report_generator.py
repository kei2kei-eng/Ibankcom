"""
Hourly Investment Report Generator
===================================
Generates beautiful HTML + text reports every hour during market hours.
Each report includes:
  - What changed since the last hour
  - Updated market analysis
  - Learning feedback from previous hours
  - Current BUY/SELL/HOLD recommendations
The report is designed for a human trader — clear, actionable, with reasoning.
"""

import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import asdict

logger = logging.getLogger(__name__)


class HourlyReportGenerator:
    """Generates hourly investment reports with learning feedback."""

    def __init__(self, openai_client=None, model="gpt-4o"):
        self.client = openai_client
        self.model = model
        self._cycle_number = 0

    def generate(self, top_50, screening_report, analysis_results, portfolio,
                 prev_hour_review=None, multi_hour_review=None, learning_context="") -> Dict:
        """
        Generate the complete hourly report.
        Each hour you get a fresh report with what changed and what to do.
        """
        self._cycle_number += 1
        report_date = datetime.now().strftime("%Y-%m-%d")
        report_time = datetime.now().strftime("%H:%M")
        report_hour_label = f"{report_time} (Cycle #{self._cycle_number})"

        # ── Build sections ──
        market_regime = screening_report.get("market_regime", "NEUTRAL")
        sector_themes = screening_report.get("sector_themes", [])
        selected = screening_report.get("selected_tickers", [])

        # Section 1: Market Overview (LLM-generated)
        market_overview = self._generate_market_overview(top_50, screening_report)

        # Section 2: Top 50 Ranking Table
        ranking_table = self._build_ranking_table(top_50)

        # Section 3: Deep Analysis for each selected stock
        stock_reports = {}
        for ticker, data in analysis_results.items():
            stock_reports[ticker] = self._build_stock_report(ticker, data)

        # Section 4: Portfolio status
        portfolio_status = portfolio.get_portfolio_summary()

        # Section 5: Action Summary (the TL;DR)
        action_summary = self._build_action_summary(analysis_results)

        report = {
            "date": report_date,
            "time": report_time,
            "hour_label": report_hour_label,
            "cycle_number": self._cycle_number,
            "market_regime": market_regime,
            "sector_themes": sector_themes,
            "market_overview": market_overview,
            "ranking_table": ranking_table,
            "selected_tickers": selected,
            "stock_reports": stock_reports,
            "portfolio": portfolio_status,
            "action_summary": action_summary,
            "prev_hour_review": prev_hour_review or {},
            "multi_hour_review": multi_hour_review or {},
            "learning_context": learning_context,
            "total_analyzed": len(analysis_results),
            "total_discovered": len(top_50),
        }

        return report

    def _generate_market_overview(self, top_50, screening_report) -> str:
        """Use LLM to write a market overview narrative."""
        if not self.client or not top_50:
            return "Market overview unavailable. Run with OpenAI API key for AI-generated analysis."

        # Count sector distribution in top 50
        sectors = {}
        bullish_count = 0
        bearish_count = 0
        for s in top_50[:20]:
            sector = s.sector
            sectors[sector] = sectors.get(sector, 0) + 1
            if "BULL" in s.recommendation:
                bullish_count += 1
            elif "BEAR" in s.recommendation:
                bearish_count += 1

        top5_summary = "\n".join([
            f"  {s.ticker} ({s.company_name}): ${s.price:.2f}, Score={s.total_score:.0f}, "
            f"RSI={s.rsi:.0f}, Signals: {', '.join(s.key_signals[:3])}"
            for s in top_50[:5]
        ])

        prompt = f"""Write a concise HOURLY market update for a stock trader. Based on the latest data:

Date/Time: {datetime.now().strftime('%Y-%m-%d %H:%M')} (Hourly Update)
Market Regime: {screening_report.get('market_regime', 'N/A')}
Sectors in Top 20: {json.dumps(sectors)}
Bullish stocks (top 20): {bullish_count}
Bearish stocks (top 20): {bearish_count}

Top 5 Stocks This Hour:
{top5_summary}

Sector Themes: {', '.join(screening_report.get('sector_themes', []))}
Watch List: {', '.join(screening_report.get('watch_list', []))}
Avoid: {', '.join(screening_report.get('avoid_list', []))}

Write 3-4 paragraphs covering:
1. What has changed in the market since the last hour
2. Which sectors are gaining/losing momentum NOW
3. Key intraday themes and price action patterns
4. What to watch for in the next hour

Be direct and actionable. Write for a day trader who checks in every hour.
Focus on INTRADAY movements and what's changing. Use simple English. No fluff."""

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a senior market strategist writing an hourly intraday briefing for an active trader."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=800,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Market overview generation error: {e}")
            return f"Market overview generation failed. Regime: {screening_report.get('market_regime', 'N/A')}"

    def _build_ranking_table(self, top_50) -> List[Dict]:
        """Build the Top 50 ranking table data."""
        table = []
        for i, s in enumerate(top_50[:50]):
            table.append({
                "rank": i + 1,
                "ticker": s.ticker,
                "company": s.company_name[:25],
                "sector": s.sector,
                "price": round(s.price, 2),
                "daily_change": round(s.daily_change_pct, 2),
                "score": round(s.total_score, 1),
                "rsi": round(s.rsi, 0),
                "recommendation": s.recommendation,
                "signals": s.key_signals[:3],
                "passed": s.passed_hard_rules,
            })
        return table

    def _build_stock_report(self, ticker, data) -> Dict:
        """Build detailed report for one stock."""
        fd = data.get("final_decision", {})
        agent_recs = data.get("agent_recommendations", {})
        indicators = data.get("indicators", {})
        company = data.get("company_info", {})
        news = data.get("news_analysis", {})

        return {
            "ticker": ticker,
            "company_name": company.get("company_name", ticker),
            "sector": company.get("sector", "Unknown"),
            "current_price": indicators.get("current_price", 0),
            "daily_change": indicators.get("daily_change_pct", 0),
            "ceo_decision": fd.get("final_action", "HOLD"),
            "ceo_confidence": fd.get("confidence", 0),
            "ceo_reasoning": fd.get("reasoning", ""),
            "target_price": fd.get("target_price"),
            "stop_loss": fd.get("stop_loss"),
            "take_profit": fd.get("take_profit"),
            "risk_level": fd.get("risk_level", "N/A"),
            "consensus": fd.get("agent_consensus", "N/A"),
            "agent_votes": {
                name.replace("_", " ").title(): {
                    "action": rec.get("action", "N/A"),
                    "confidence": rec.get("confidence", 0),
                    "risk": rec.get("risk_level", "N/A"),
                }
                for name, rec in agent_recs.items()
            },
            "rsi": indicators.get("rsi", 0),
            "macd": indicators.get("macd", 0),
            "sma_50": indicators.get("sma_50", 0),
            "sma_200": indicators.get("sma_200", 0),
            "volatility": indicators.get("volatility_30d", 0),
            "pe_ratio": company.get("pe_ratio"),
            "beta": company.get("beta"),
            "analyst_rating": company.get("analyst_rating"),
            "52w_high": company.get("52w_high"),
            "52w_low": company.get("52w_low"),
            "news_sentiment": news.get("sentiment_label", "N/A"),
            "news_sentiment_score": news.get("overall_sentiment", 0),
            "news_themes": news.get("key_themes", []),
        }

    def _build_action_summary(self, analysis_results) -> Dict:
        """Build the TL;DR action summary."""
        buys = []
        sells = []
        holds = []

        for ticker, data in analysis_results.items():
            fd = data.get("final_decision", {})
            action = fd.get("final_action", "HOLD")
            conf = fd.get("confidence", 0)
            reason = fd.get("reasoning", "")[:200]
            price = data.get("indicators", {}).get("current_price", 0)

            entry = {
                "ticker": ticker,
                "confidence": round(conf, 2),
                "reasoning": reason,
                "price": price,
                "target": fd.get("target_price"),
                "stop_loss": fd.get("stop_loss"),
                "risk": fd.get("risk_level", "N/A"),
            }

            if action == "BUY":
                buys.append(entry)
            elif action == "SELL":
                sells.append(entry)
            else:
                holds.append(entry)

        return {
            "buy_recommendations": buys,
            "sell_recommendations": sells,
            "hold_recommendations": holds,
            "total_buy": len(buys),
            "total_sell": len(sells),
            "total_hold": len(holds),
        }

    # ── SAVE REPORTS ──

    def save(self, report: Dict):
        """Save report as HTML and text files. Keeps both latest and timestamped archive."""
        self._save_html(report)
        self._save_text(report)

        # Also save a timestamped copy for history
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        self._save_html(report, filename=f"reports/report_{timestamp}.html")
        self._save_text(report, filename=f"reports/report_{timestamp}.txt")

        logger.info("📄 Report saved: report_latest.html + report_latest.txt (and archived)")

    def _save_text(self, report: Dict, filename: str = "report_latest.txt"):
        """Save plain text version."""
        import os
        os.makedirs(os.path.dirname(filename) if "/" in filename else ".", exist_ok=True)

        lines = []
        lines.append("=" * 70)
        lines.append(f"🏦 AI INVESTMENT BANK — HOURLY REPORT")
        lines.append(f"   {report['date']} {report['time']}  |  {report.get('hour_label', '')}")
        lines.append(f"   Cycle #{report.get('cycle_number', '?')}")
        lines.append("=" * 70)

        # Previous hour review
        prev = report.get("prev_hour_review", {})
        if prev.get("reviews"):
            lines.append(f"\n{'='*70}")
            lines.append(f"📊 WHAT CHANGED SINCE LAST HOUR ({prev.get('hour_label', 'Previous')})")
            lines.append(f"{'='*70}")
            lines.append(f"  Accuracy: {prev.get('accuracy', 0):.0%} ({prev.get('correct_count', 0)}/{prev.get('total_count', 0)})")
            lines.append(f"  {prev.get('learning_notes', '')}")
            lines.append("")
            for r in prev["reviews"]:
                icon = "✅" if r["was_correct"] else "❌"
                lines.append(f"  {icon} {r['ticker']:6s} {r['prev_action']:4s} → "
                           f"${r['prev_price']:.2f} → ${r['current_price']:.2f} ({r['change_pct']:+.2f}%)")
                if r.get("target_hit"):
                    lines.append(f"      🎯 Target price hit!")
                if r.get("stop_hit"):
                    lines.append(f"      🛑 Stop loss hit!")

        # Multi-hour trend
        multi = report.get("multi_hour_review", {})
        if multi.get("accuracy_trend"):
            lines.append(f"\n  Multi-Hour Trend: {multi.get('trend', 'N/A').upper()}")
            for t in multi["accuracy_trend"]:
                lines.append(f"    {t.get('hour', '?')}: {t.get('accuracy', 0):.0%} accuracy ({t.get('total', 0)} picks)")
            lines.append(f"  {multi.get('learning_insights', '')}")

        # Market overview
        lines.append(f"\n📰 MARKET OVERVIEW (Regime: {report['market_regime']})")
        lines.append("-" * 70)
        lines.append(report.get("market_overview", "N/A"))

        # Action summary
        summary = report.get("action_summary", {})
        lines.append(f"\n{'='*70}")
        lines.append(f"🎯 ACTION SUMMARY — THIS HOUR")
        lines.append(f"{'='*70}")

        if summary.get("total_buy", 0) > 0:
            lines.append(f"\n  🟢 BUY RECOMMENDATIONS ({summary['total_buy']}):")
            for b in summary["buy_recommendations"]:
                lines.append(f"    • {b['ticker']:6s} @ ${b['price']:.2f}  "
                           f"(conf: {b['confidence']:.0%}, risk: {b['risk']})")
                if b.get("target"):
                    lines.append(f"      Target: ${b['target']:.2f} | Stop Loss: ${b.get('stop_loss', 'N/A')}")
                lines.append(f"      Why: {b['reasoning'][:150]}")

        if summary.get("total_sell", 0) > 0:
            lines.append(f"\n  🔴 SELL RECOMMENDATIONS ({summary['total_sell']}):")
            for s in summary["sell_recommendations"]:
                lines.append(f"    • {s['ticker']:6s} @ ${s['price']:.2f}  "
                           f"(conf: {s['confidence']:.0%}, risk: {s['risk']})")
                lines.append(f"      Why: {s['reasoning'][:150]}")

        if summary.get("total_hold", 0) > 0:
            lines.append(f"\n  🟡 HOLD ({summary['total_hold']}): {', '.join(h['ticker'] for h in summary['hold_recommendations'])}")

        # Top 50
        lines.append(f"\n{'='*70}")
        lines.append(f"📊 TOP 50 RANKED STOCKS")
        lines.append(f"{'='*70}")
        lines.append(f"{'#':>3} {'Ticker':<7} {'Price':>10} {'Chg%':>7} {'Score':>6} {'RSI':>5} {'Rec':<17}")
        lines.append("-" * 70)
        for row in report.get("ranking_table", []):
            lines.append(f"{row['rank']:>3} {row['ticker']:<7} ${row['price']:>9.2f} "
                        f"{row['daily_change']:>+6.2f}% {row['score']:>6.1f} {row['rsi']:>5.0f} "
                        f"{row['recommendation']:<17}")

        # Detailed analysis
        for ticker, sr in report.get("stock_reports", {}).items():
            lines.append(f"\n{'='*70}")
            lines.append(f"🔍 DEEP ANALYSIS: {sr['company_name']} ({ticker})")
            lines.append(f"{'='*70}")
            lines.append(f"  CEO Decision: {sr['ceo_decision']} (confidence: {sr['ceo_confidence']:.0%})")
            lines.append(f"  Risk Level: {sr['risk_level']}")
            lines.append(f"  Consensus: {sr['consensus']}")
            if sr.get("target_price"):
                lines.append(f"  Target: ${sr['target_price']:.2f} | Stop Loss: ${sr.get('stop_loss', 'N/A')}")
            lines.append(f"\n  CEO Reasoning:\n  {sr['ceo_reasoning'][:500]}")

            lines.append(f"\n  Agent Votes:")
            for agent_name, vote in sr.get("agent_votes", {}).items():
                lines.append(f"    {agent_name:20s}: {vote['action']:5s} "
                           f"(conf: {vote['confidence']:.0%}, risk: {vote['risk']})")

            lines.append(f"\n  Technicals:")
            lines.append(f"    RSI: {sr['rsi']:.0f} | MACD: {sr['macd']:.4f} | Beta: {sr.get('beta', 'N/A')}")
            lines.append(f"    SMA50: ${sr['sma_50']:.2f} | SMA200: ${sr['sma_200']:.2f}")
            lines.append(f"    P/E: {sr.get('pe_ratio', 'N/A')} | Analyst: {sr.get('analyst_rating', 'N/A')}")
            lines.append(f"    52W Range: ${sr.get('52w_low', 0):.2f} - ${sr.get('52w_high', 0):.2f}")

            if sr.get("news_sentiment") != "N/A":
                lines.append(f"\n  News Sentiment: {sr['news_sentiment']} ({sr.get('news_sentiment_score', 0):.2f})")
                if sr.get("news_themes"):
                    lines.append(f"  News Themes: {', '.join(sr['news_themes'][:5])}")

        # Learning insights
        learning = report.get("learning_context", "")
        if learning:
            lines.append(f"\n{'='*70}")
            lines.append(f"📚 LEARNING INSIGHTS")
            lines.append(f"{'='*70}")
            lines.append(learning[:1500])

        lines.append(f"\n{'='*70}")
        lines.append(f"⚠️  This is AI-generated analysis for reference only.")
        lines.append(f"   Not financial advice. Always do your own research.")
        lines.append(f"   Hourly report — Next update in ~60 minutes.")
        lines.append(f"{'='*70}")

        text = "\n".join(lines)
        with open(filename, "w") as f:
            f.write(text)
        return text

    def _save_html(self, report: Dict, filename: str = "report_latest.html"):
        """Save beautiful HTML report."""
        import os
        os.makedirs(os.path.dirname(filename) if "/" in filename else ".", exist_ok=True)

        summary = report.get("action_summary", {})
        ranking = report.get("ranking_table", [])

        # Build "What Changed" section
        prev = report.get("prev_hour_review", {})
        prev_section = ""
        if prev.get("reviews"):
            review_rows = ""
            for r in prev["reviews"]:
                icon = "✅" if r["was_correct"] else "❌"
                row_class = "positive" if r["change_pct"] > 0 else "negative"
                target_note = ""
                if r.get("target_hit"):
                    target_note = ' <span class="positive">🎯 Target Hit!</span>'
                if r.get("stop_hit"):
                    target_note = ' <span class="negative">🛑 Stop Hit!</span>'
                review_rows += f"""
                <tr>
                    <td>{icon}</td>
                    <td><strong>{r['ticker']}</strong></td>
                    <td>{r['prev_action']}</td>
                    <td>${r['prev_price']:.2f}</td>
                    <td>${r['current_price']:.2f}</td>
                    <td class="{row_class}">{r['change_pct']:+.2f}%</td>
                    <td>{r['prev_confidence']:.0%}</td>
                    <td>{target_note}</td>
                </tr>"""

            prev_section = f"""
            <h2>📊 What Changed Since Last Hour ({prev.get('hour_label', 'Previous')})</h2>
            <div class="overview">
                <p><strong>Accuracy:</strong> <span class="{'positive' if prev['accuracy'] > 0.5 else 'negative'}">{prev['accuracy']:.0%}</span>
                ({prev.get('correct_count', 0)}/{prev.get('total_count', 0)} correct)</p>
                <p><strong>Learning:</strong> {prev.get('learning_notes', '')}</p>
            </div>
            <table>
                <tr><th></th><th>Ticker</th><th>Action</th><th>Prev Price</th><th>Now</th><th>Change</th><th>Conf</th><th>Notes</th></tr>
                {review_rows}
            </table>"""

        # Multi-hour trend
        multi = report.get("multi_hour_review", {})
        trend_section = ""
        if multi.get("accuracy_trend"):
            trend_class = "positive" if multi.get("trend") == "improving" else "negative" if multi.get("trend") == "declining" else "hold-color"
            trend_rows = ""
            for t in multi["accuracy_trend"]:
                trend_rows += f"""
                <tr>
                    <td>{t.get('hour', '?')}</td>
                    <td class="{'positive' if t.get('accuracy', 0) > 0.5 else 'negative'}">{t.get('accuracy', 0):.0%}</td>
                    <td>{t.get('total', 0)} picks</td>
                </tr>"""
            trend_section = f"""
            <h2>📈 Multi-Hour Accuracy Trend: <span class="{trend_class}">{multi.get('trend', 'N/A').upper()}</span></h2>
            <table>
                <tr><th>Hour</th><th>Accuracy</th><th>Picks</th></tr>
                {trend_rows}
            </table>
            <div class="overview"><p>{multi.get('learning_insights', '')}</p></div>"""

        # Learning context section
        learning = report.get("learning_context", "")
        learning_section = ""
        if learning and len(learning) > 50:
            learning_section = f"""
            <h2>📚 Learning Insights This Hour</h2>
            <div class="overview"><pre style="white-space: pre-wrap; color: #ccc;">{learning[:2000]}</pre></div>"""

        # Build buy cards
        buy_cards = ""
        for b in summary.get("buy_recommendations", []):
            buy_cards += f"""
            <div class="card buy">
                <div class="card-header">
                    <span class="ticker">{b['ticker']}</span>
                    <span class="price">${b['price']:.2f}</span>
                    <span class="conf">Confidence: {b['confidence']:.0%}</span>
                </div>
                <div class="card-body">
                    <p><strong>Risk:</strong> {b['risk']}</p>
                    {"<p><strong>Target:</strong> $" + f"{b['target']:.2f}" + " | <strong>Stop Loss:</strong> $" + f"{b.get('stop_loss', 'N/A')}" + "</p>" if b.get('target') else ""}
                    <p class="reasoning">{b['reasoning'][:300]}</p>
                </div>
            </div>"""

        sell_cards = ""
        for s in summary.get("sell_recommendations", []):
            sell_cards += f"""
            <div class="card sell">
                <div class="card-header">
                    <span class="ticker">{s['ticker']}</span>
                    <span class="price">${s['price']:.2f}</span>
                    <span class="conf">Confidence: {s['confidence']:.0%}</span>
                </div>
                <div class="card-body">
                    <p class="reasoning">{s['reasoning'][:300]}</p>
                </div>
            </div>"""

        # Build ranking rows
        ranking_rows = ""
        for row in ranking:
            rec_class = "buy" if "BULL" in row["recommendation"] else "sell" if "BEAR" in row["recommendation"] else "hold"
            ranking_rows += f"""
            <tr class="{rec_class}">
                <td>{row['rank']}</td>
                <td><strong>{row['ticker']}</strong></td>
                <td>{row['company'][:20]}</td>
                <td>${row['price']:.2f}</td>
                <td class="{'positive' if row['daily_change'] > 0 else 'negative'}">{row['daily_change']:+.2f}%</td>
                <td>{row['score']:.0f}</td>
                <td>{row['rsi']:.0f}</td>
                <td>{row['recommendation']}</td>
            </tr>"""

        # Build detailed stock sections
        stock_sections = ""
        for ticker, sr in report.get("stock_reports", {}).items():
            decision_class = "buy" if sr["ceo_decision"] == "BUY" else "sell" if sr["ceo_decision"] == "SELL" else "hold"
            agent_rows = ""
            for aname, avote in sr.get("agent_votes", {}).items():
                agent_rows += f"<tr><td>{aname}</td><td class='{avote['action'].lower()}'>{avote['action']}</td><td>{avote['confidence']:.0%}</td><td>{avote['risk']}</td></tr>"

            stock_sections += f"""
            <div class="stock-detail">
                <h2 class="{decision_class}">🎯 {sr['company_name']} ({ticker}) — {sr['ceo_decision']}</h2>
                <div class="detail-grid">
                    <div class="detail-card">
                        <h3>CEO Decision</h3>
                        <p class="big-decision {decision_class}">{sr['ceo_decision']}</p>
                        <p>Confidence: {sr['ceo_confidence']:.0%} | Risk: {sr['risk_level']} | Consensus: {sr['consensus']}</p>
                        {"<p>Target: $" + f"{sr['target_price']:.2f}" + " | Stop Loss: $" + f"{sr.get('stop_loss', 'N/A')}" + "</p>" if sr.get('target_price') else ""}
                        <p class="reasoning"><strong>Why:</strong> {sr['ceo_reasoning'][:600]}</p>
                    </div>
                    <div class="detail-card">
                        <h3>Agent Votes</h3>
                        <table class="agent-table"><tr><th>Agent</th><th>Vote</th><th>Conf</th><th>Risk</th></tr>{agent_rows}</table>
                    </div>
                    <div class="detail-card">
                        <h3>Technicals</h3>
                        <p>RSI: {sr['rsi']:.0f} | MACD: {sr['macd']:.4f} | Beta: {sr.get('beta', 'N/A')}</p>
                        <p>P/E: {sr.get('pe_ratio', 'N/A')} | Analyst: {sr.get('analyst_rating', 'N/A')}</p>
                        <p>52W: ${sr.get('52w_low', 0):.2f} — ${sr.get('52w_high', 0):.2f}</p>
                    </div>
                    {"<div class='detail-card'><h3>News</h3><p>Sentiment: " + sr.get('news_sentiment', 'N/A') + " (" + f"{sr.get('news_sentiment_score', 0):.2f}" + ")</p><p>Themes: " + ', '.join(sr.get('news_themes', [])) + "</p></div>" if sr.get('news_sentiment') != 'N/A' else ""}
                </div>
            </div>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🏦 AI iBank Hourly Report — {report['date']} {report['time']}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #ff6b35; font-size: 28px; margin-bottom: 5px; }}
h2 {{ color: #fff; font-size: 22px; margin: 20px 0 10px; padding-bottom: 8px; border-bottom: 2px solid #333; }}
h3 {{ color: #aaa; font-size: 16px; margin-bottom: 8px; }}
.subtitle {{ color: #888; font-size: 14px; margin-bottom: 20px; }}
.cycle-badge {{ background: #ff6b35; color: #000; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; }}
.overview {{ background: #1a1a2e; padding: 20px; border-radius: 10px; margin: 15px 0; line-height: 1.7; }}
.overview p {{ margin-bottom: 12px; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin: 15px 0; }}
.stat-box {{ background: #1a1a2e; padding: 15px; border-radius: 10px; text-align: center; }}
.stat-box .num {{ font-size: 32px; font-weight: bold; }}
.stat-box.buy .num {{ color: #00d4aa; }}
.stat-box.sell .num {{ color: #ff4757; }}
.stat-box.hold .num {{ color: #ffa502; }}
.stat-box.accuracy .num {{ color: #a29bfe; }}
.stat-box.trend .num {{ font-size: 18px; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 15px; margin: 15px 0; }}
.card {{ background: #1a1a2e; border-radius: 10px; overflow: hidden; }}
.card-header {{ padding: 15px; display: flex; justify-content: space-between; align-items: center; }}
.card.buy .card-header {{ background: linear-gradient(135deg, #00b894, #00cec9); color: #000; }}
.card.sell .card-header {{ background: linear-gradient(135deg, #e17055, #d63031); color: #fff; }}
.card-body {{ padding: 15px; }}
.ticker {{ font-size: 20px; font-weight: bold; }}
.price {{ font-size: 18px; }}
.conf {{ font-size: 14px; opacity: 0.9; }}
.reasoning {{ color: #ccc; font-size: 14px; line-height: 1.5; margin-top: 8px; }}
table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
th {{ background: #2d3436; color: #dfe6e9; padding: 10px; text-align: left; font-size: 13px; }}
td {{ padding: 8px 10px; border-bottom: 1px solid #2d3436; font-size: 13px; }}
tr.buy td {{ color: #00d4aa; }}
tr.sell td {{ color: #ff4757; }}
.positive {{ color: #00d4aa !important; }}
.negative {{ color: #ff4757 !important; }}
.hold-color {{ color: #ffa502 !important; }}
.stock-detail {{ background: #111; border-radius: 10px; padding: 20px; margin: 15px 0; }}
.big-decision {{ font-size: 36px; font-weight: bold; text-align: center; padding: 10px; }}
.big-decision.buy {{ color: #00d4aa; }}
.big-decision.sell {{ color: #ff4757; }}
.big-decision.hold {{ color: #ffa502; }}
.detail-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; margin-top: 15px; }}
.detail-card {{ background: #1a1a2e; padding: 15px; border-radius: 8px; }}
.agent-table th, .agent-table td {{ font-size: 12px; padding: 5px 8px; }}
.disclaimer {{ background: #2d3436; padding: 15px; border-radius: 8px; color: #636e72; font-size: 12px; margin-top: 30px; text-align: center; }}
.countdown {{ background: #1a1a2e; padding: 10px 20px; border-radius: 8px; display: inline-block; margin: 10px 0; color: #ffa502; font-size: 14px; }}
</style>
</head>
<body>

<h1>🏦 AI Investment Bank — Hourly Report <span class="cycle-badge">#{report.get('cycle_number', '?')}</span></h1>
<p class="subtitle">{report['date']} {report['time']} | Market Regime: {report['market_regime']} | {report['total_discovered']} stocks scanned | <span class="countdown">⏱ Next report in ~60 min</span></p>

<div class="summary-grid">
    <div class="stat-box buy"><div class="num">{summary.get('total_buy', 0)}</div><div>🟢 BUY</div></div>
    <div class="stat-box sell"><div class="num">{summary.get('total_sell', 0)}</div><div>🔴 SELL</div></div>
    <div class="stat-box hold"><div class="num">{summary.get('total_hold', 0)}</div><div>🟡 HOLD</div></div>
    <div class="stat-box accuracy"><div class="num">{prev.get('accuracy', '—') if prev.get('reviews') else '—'}</div><div>📊 Prev Hour Acc</div></div>
    <div class="stat-box trend"><div class="num" style="color: {'#00d4aa' if multi.get('trend')=='improving' else '#ff4757' if multi.get('trend')=='declining' else '#ffa502'}">{multi.get('trend', '—').upper() if multi.get('trend') else '—'}</div><div>📈 Trend</div></div>
</div>

{prev_section}
{trend_section}

<h2>📰 Hourly Market Update</h2>
<div class="overview">{report.get('market_overview', 'N/A')}</div>

<h2>🎯 Buy Recommendations — This Hour</h2>
<div class="cards">{buy_cards if buy_cards else "<p>No strong buy signals this hour.</p>"}</div>

{"<h2>🔴 Sell Recommendations</h2><div class='cards'>" + sell_cards + "</div>" if sell_cards else ""}

<h2>📊 Top 50 Ranked Stocks</h2>
<table>
<tr><th>#</th><th>Ticker</th><th>Company</th><th>Price</th><th>Change</th><th>Score</th><th>RSI</th><th>Signal</th></tr>
{ranking_rows}
</table>

<h2>🔍 Deep Analysis — Top Picks This Hour</h2>
{stock_sections}

{learning_section}

<div class="disclaimer">
⚠️ DISCLAIMER: This is AI-generated HOURLY analysis for YOUR reference only.<br>
This is NOT financial advice. Always do your own research before trading.<br>
AI models can be wrong. Past performance does not guarantee future results.<br>
Each hour the system reviews its previous picks and learns from outcomes.
</div>

</body>
</html>"""

        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)
        return html

    # ── TELEGRAM SENDING ──

    def send_report(self, report: Dict):
        """Send the report via Telegram."""
        from telegram_sender import TelegramSender
        sender = TelegramSender()
        if not sender.enabled:
            logger.info("📱 Telegram not configured. Report saved locally only.")
            return False
        return sender.send_report(report)

    # ── EMAIL SENDING (kept as fallback) ──

    def send_email(self, report: Dict):
        """Send the report via email (fallback — Telegram is preferred)."""
        email_to = os.getenv("REPORT_EMAIL", "")
        if not email_to:
            logger.info("📧 No REPORT_EMAIL set. Skipping email.")
            return False

        email_from = os.getenv("SMTP_FROM", "")
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")

        if not all([email_from, smtp_user, smtp_pass]):
            logger.info("📧 Email not configured. Skipping email.")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🏦 AI iBank Hourly Report — {report['date']} {report['time']} (#{report.get('cycle_number', '?')})"
            msg["From"] = email_from
            msg["To"] = email_to

            # Text version
            with open("report_latest.txt", "r") as f:
                text_content = f.read()
            msg.attach(MIMEText(text_content, "plain"))

            # HTML version
            with open("report_latest.html", "r") as f:
                html_content = f.read()
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(email_from, email_to, msg.as_string())

            logger.info(f"📧 Report sent to {email_to}")
            return True

        except Exception as e:
            logger.error(f"📧 Email send failed: {e}")
            logger.info("   Report saved locally: report_latest.html")
            return False
