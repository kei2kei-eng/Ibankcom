"""
Decision Journal
================
Records all trading decisions and their outcomes for learning.
Uses SQLite for persistence.
"""

import sqlite3
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class DecisionJournal:
    """
    Persists all decisions and outcomes. This is the memory of the system.
    Every trade, every analysis, every outcome is recorded here.
    """

    def __init__(self, db_path: str = "decision_journal.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                quantity REAL DEFAULT 0,
                price REAL DEFAULT 0,
                confidence REAL DEFAULT 0,
                final_decision_json TEXT,
                agent_recommendations_json TEXT,
                market_data_json TEXT,
                news_data_json TEXT,
                learning_context TEXT,
                portfolio_snapshot_json TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                ticker TEXT NOT NULL,
                entry_price REAL,
                current_price REAL,
                price_change_pct REAL,
                max_favorable_pct REAL,
                max_adverse_pct REAL,
                holding_period_hours REAL,
                outcome_label TEXT,
                notes TEXT,
                FOREIGN KEY (decision_id) REFERENCES decisions(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS agent_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                agent_type TEXT NOT NULL,
                ticker TEXT NOT NULL,
                recommended_action TEXT,
                confidence REAL,
                was_correct INTEGER DEFAULT 0,
                accuracy_running REAL DEFAULT 0,
                weight REAL DEFAULT 1.0,
                parameters_json TEXT,
                notes TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS learning_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                adjustment_type TEXT NOT NULL,
                agent_name TEXT,
                parameter_name TEXT,
                old_value TEXT,
                new_value TEXT,
                reason TEXT,
                performance_data_json TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS market_regimes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                regime TEXT NOT NULL,
                vix_level REAL,
                spy_trend TEXT,
                sector_performance_json TEXT,
                notes TEXT
            )
        """)

        conn.commit()
        conn.close()
        logger.info(f"Decision journal initialized at {self.db_path}")

    def record_decision(
        self,
        ticker: str,
        action: str,
        quantity: float,
        price: float,
        confidence: float,
        final_decision: Dict,
        agent_recommendations: Dict,
        market_data: Dict,
        news_data: Dict,
        learning_context: str,
        portfolio_snapshot: Dict,
    ) -> int:
        """Record a trading decision."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            INSERT INTO decisions (
                timestamp, ticker, action, quantity, price, confidence,
                final_decision_json, agent_recommendations_json,
                market_data_json, news_data_json, learning_context,
                portfolio_snapshot_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            ticker,
            action,
            quantity,
            price,
            confidence,
            json.dumps(final_decision, default=str),
            json.dumps(agent_recommendations, default=str),
            json.dumps(market_data, default=str),
            json.dumps(news_data, default=str),
            learning_context,
            json.dumps(portfolio_snapshot, default=str),
        ))

        decision_id = c.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Decision #{decision_id} recorded: {action} {quantity} {ticker} @ ${price:.2f}")
        return decision_id

    def record_outcome(
        self,
        decision_id: int,
        ticker: str,
        entry_price: float,
        current_price: float,
        max_favorable_pct: float = 0,
        max_adverse_pct: float = 0,
        holding_period_hours: float = 0,
    ) -> int:
        """Record the outcome of a past decision."""
        price_change_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

        # Determine outcome label
        if price_change_pct > 2:
            outcome = "PROFITABLE"
        elif price_change_pct < -2:
            outcome = "UNPROFITABLE"
        else:
            outcome = "NEUTRAL"

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            INSERT INTO outcomes (
                decision_id, timestamp, ticker, entry_price, current_price,
                price_change_pct, max_favorable_pct, max_adverse_pct,
                holding_period_hours, outcome_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            decision_id,
            datetime.now().isoformat(),
            ticker,
            entry_price,
            current_price,
            price_change_pct,
            max_favorable_pct,
            max_adverse_pct,
            holding_period_hours,
            outcome,
        ))

        outcome_id = c.lastrowid
        conn.commit()
        conn.close()

        return outcome_id

    def record_agent_performance(
        self,
        agent_name: str,
        agent_type: str,
        ticker: str,
        recommended_action: str,
        confidence: float,
        was_correct: bool,
        accuracy_running: float,
        weight: float,
        parameters: Dict,
        notes: str = "",
    ):
        """Record individual agent performance."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            INSERT INTO agent_performance (
                timestamp, agent_name, agent_type, ticker,
                recommended_action, confidence, was_correct,
                accuracy_running, weight, parameters_json, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            agent_name,
            agent_type,
            ticker,
            recommended_action,
            confidence,
            1 if was_correct else 0,
            accuracy_running,
            weight,
            json.dumps(parameters),
            notes,
        ))

        conn.commit()
        conn.close()

    def record_learning_adjustment(
        self,
        adjustment_type: str,
        agent_name: str,
        parameter_name: str,
        old_value: str,
        new_value: str,
        reason: str,
        performance_data: Dict = None,
    ):
        """Record a learning adjustment made to an agent."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            INSERT INTO learning_adjustments (
                timestamp, adjustment_type, agent_name, parameter_name,
                old_value, new_value, reason, performance_data_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            adjustment_type,
            agent_name,
            parameter_name,
            str(old_value),
            str(new_value),
            reason,
            json.dumps(performance_data or {}),
        ))

        conn.commit()
        conn.close()

    def get_recent_decisions(self, limit: int = 20, ticker: str = None) -> List[Dict]:
        """Get recent decisions with their outcomes."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        if ticker:
            c.execute("""
                SELECT d.*, o.price_change_pct, o.outcome_label, o.max_favorable_pct, o.max_adverse_pct
                FROM decisions d
                LEFT JOIN outcomes o ON d.id = o.decision_id
                WHERE d.ticker = ?
                ORDER BY d.timestamp DESC LIMIT ?
            """, (ticker, limit))
        else:
            c.execute("""
                SELECT d.*, o.price_change_pct, o.outcome_label, o.max_favorable_pct, o.max_adverse_pct
                FROM decisions d
                LEFT JOIN outcomes o ON d.id = o.decision_id
                ORDER BY d.timestamp DESC LIMIT ?
            """, (limit,))

        rows = c.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_agent_performance_history(self, agent_name: str = None, limit: int = 50) -> List[Dict]:
        """Get agent performance history."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        if agent_name:
            c.execute("""
                SELECT * FROM agent_performance
                WHERE agent_name = ?
                ORDER BY timestamp DESC LIMIT ?
            """, (agent_name, limit))
        else:
            c.execute("""
                SELECT * FROM agent_performance
                ORDER BY timestamp DESC LIMIT ?
            """, (limit,))

        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_learning_adjustments(self, limit: int = 50) -> List[Dict]:
        """Get history of learning adjustments."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("""
            SELECT * FROM learning_adjustments
            ORDER BY timestamp DESC LIMIT ?
        """, (limit,))

        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_decision_for_review(self, decision_id: int) -> Optional[Dict]:
        """Get a specific decision with full details for review."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,))
        row = c.fetchone()

        if row:
            result = dict(row)
            # Parse JSON fields
            for key in ["final_decision_json", "agent_recommendations_json",
                        "market_data_json", "news_data_json", "portfolio_snapshot_json"]:
                if result.get(key):
                    try:
                        result[key.replace("_json", "")] = json.loads(result[key])
                    except json.JSONDecodeError:
                        result[key.replace("_json", "")] = {}

            # Get outcome
            c.execute("SELECT * FROM outcomes WHERE decision_id = ?", (decision_id,))
            outcome = c.fetchone()
            result["outcome"] = dict(outcome) if outcome else None

            conn.close()
            return result

        conn.close()
        return None

    def get_performance_summary(self) -> Dict:
        """Get overall system performance summary."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        summary = {}

        # Total decisions
        c.execute("SELECT COUNT(*) FROM decisions")
        summary["total_decisions"] = c.fetchone()[0]

        # Outcomes
        c.execute("""
            SELECT outcome_label, COUNT(*) as count, AVG(price_change_pct) as avg_change
            FROM outcomes
            GROUP BY outcome_label
        """)
        summary["outcomes"] = {row[0]: {"count": row[1], "avg_change": row[2]} for row in c.fetchall()}

        # By action
        c.execute("""
            SELECT action, COUNT(*) as count
            FROM decisions
            GROUP BY action
        """)
        summary["by_action"] = {row[0]: row[1] for row in c.fetchall()}

        # Agent accuracies
        c.execute("""
            SELECT agent_name, 
                   COUNT(*) as total,
                   SUM(was_correct) as correct,
                   AVG(accuracy_running) as avg_accuracy
            FROM agent_performance
            GROUP BY agent_name
        """)
        summary["agent_accuracy"] = {
            row[0]: {"total": row[1], "correct": row[2], "avg_accuracy": row[3]}
            for row in c.fetchall()
        }

        conn.close()
        return summary
