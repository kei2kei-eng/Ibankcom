"""
Portfolio Manager
=================
Manages the trading portfolio, positions, and cash.
"""

import json
import logging
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
import os

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents a single stock position."""
    ticker: str
    shares: float
    avg_cost: float
    current_price: float
    sector: str = "Unknown"
    entry_date: str = ""
    stop_loss: float = 0.0
    take_profit: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = float('inf')

    @property
    def value(self) -> float:
        return self.shares * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.shares * self.avg_cost

    @property
    def pnl(self) -> float:
        return self.value - self.cost_basis

    @property
    def pnl_pct(self) -> float:
        return ((self.current_price - self.avg_cost) / self.avg_cost * 100) if self.avg_cost > 0 else 0

    def to_dict(self) -> Dict:
        return {
            "ticker": self.ticker,
            "shares": self.shares,
            "avg_cost": self.avg_cost,
            "current_price": self.current_price,
            "value": self.value,
            "cost_basis": self.cost_basis,
            "pnl": self.pnl,
            "pnl_pct": round(self.pnl_pct, 2),
            "sector": self.sector,
            "entry_date": self.entry_date,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
        }


class PortfolioManager:
    """
    Manages the simulated portfolio with cash, positions, and trade execution.
    This is a PAPER TRADING system — no real money is at risk.
    """

    def __init__(self, initial_capital: float = 1_000_000, state_file: str = "portfolio_state.json"):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[Dict] = []
        self.state_file = state_file

        # Try to load saved state
        self.load_state()

    def buy(self, ticker: str, shares: float, price: float, sector: str = "Unknown",
            stop_loss: float = 0, take_profit: float = 0) -> Dict:
        """Execute a BUY order."""
        cost = shares * price

        if cost > self.cash:
            # Adjust shares to what we can afford
            shares = int(self.cash / price)
            cost = shares * price
            if shares == 0:
                return {"success": False, "reason": "Insufficient cash", "shares": 0}

        # Update or create position
        if ticker in self.positions:
            pos = self.positions[ticker]
            total_cost = pos.cost_basis + cost
            total_shares = pos.shares + shares
            pos.avg_cost = total_cost / total_shares if total_shares > 0 else 0
            pos.shares = total_shares
            pos.current_price = price
            pos.highest_price = max(pos.highest_price, price)
            pos.lowest_price = min(pos.lowest_price, price)
            if stop_loss > 0:
                pos.stop_loss = stop_loss
            if take_profit > 0:
                pos.take_profit = take_profit
        else:
            self.positions[ticker] = Position(
                ticker=ticker,
                shares=shares,
                avg_cost=price,
                current_price=price,
                sector=sector,
                entry_date=datetime.now().strftime("%Y-%m-%d"),
                stop_loss=stop_loss,
                take_profit=take_profit,
                highest_price=price,
                lowest_price=price,
            )

        self.cash -= cost

        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "action": "BUY",
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "cost": cost,
            "remaining_cash": self.cash,
        }
        self.trade_history.append(trade_record)

        logger.info(f"BUY {shares} {ticker} @ ${price:.2f} = ${cost:,.2f}")
        self.save_state()
        return {"success": True, "shares": shares, "cost": cost}

    def sell(self, ticker: str, shares: float, price: float) -> Dict:
        """Execute a SELL order."""
        if ticker not in self.positions:
            return {"success": False, "reason": "No position", "shares": 0}

        pos = self.positions[ticker]
        shares = min(shares, pos.shares)

        if shares == 0:
            return {"success": False, "reason": "No shares to sell", "shares": 0}

        proceeds = shares * price
        self.cash += proceeds

        pos.shares -= shares
        pos.current_price = price

        if pos.shares <= 0:
            del self.positions[ticker]

        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "action": "SELL",
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "proceeds": proceeds,
            "remaining_cash": self.cash,
        }
        self.trade_history.append(trade_record)

        logger.info(f"SELL {shares} {ticker} @ ${price:.2f} = ${proceeds:,.2f}")
        self.save_state()
        return {"success": True, "shares": shares, "proceeds": proceeds}

    def update_prices(self, prices: Dict[str, float]):
        """Update current prices for all positions."""
        for ticker, price in prices.items():
            if ticker in self.positions:
                pos = self.positions[ticker]
                pos.current_price = price
                pos.highest_price = max(pos.highest_price, price)
                pos.lowest_price = min(pos.lowest_price, price)

    def check_stop_losses(self) -> List[Dict]:
        """Check and trigger stop-loss orders."""
        triggered = []
        for ticker, pos in list(self.positions.items()):
            if pos.stop_loss > 0 and pos.current_price <= pos.stop_loss:
                logger.warning(f"STOP LOSS triggered for {ticker} @ ${pos.current_price:.2f}")
                result = self.sell(ticker, pos.shares, pos.current_price)
                triggered.append({
                    "ticker": ticker,
                    "type": "STOP_LOSS",
                    "price": pos.current_price,
                    "result": result,
                })
        return triggered

    def check_take_profits(self) -> List[Dict]:
        """Check and trigger take-profit orders."""
        triggered = []
        for ticker, pos in list(self.positions.items()):
            if pos.take_profit > 0 and pos.current_price >= pos.take_profit:
                logger.info(f"TAKE PROFIT triggered for {ticker} @ ${pos.current_price:.2f}")
                result = self.sell(ticker, pos.shares, pos.current_price)
                triggered.append({
                    "ticker": ticker,
                    "type": "TAKE_PROFIT",
                    "price": pos.current_price,
                    "result": result,
                })
        return triggered

    @property
    def total_value(self) -> float:
        return self.cash + sum(p.value for p in self.positions.values())

    @property
    def invested(self) -> float:
        return sum(p.value for p in self.positions.values())

    @property
    def total_pnl(self) -> float:
        return self.total_value - self.initial_capital

    @property
    def total_pnl_pct(self) -> float:
        return (self.total_value - self.initial_capital) / self.initial_capital * 100

    @property
    def exposure_pct(self) -> float:
        return self.invested / self.total_value * 100 if self.total_value > 0 else 0

    @property
    def num_positions(self) -> int:
        return len(self.positions)

    def get_portfolio_summary(self) -> Dict:
        """Get full portfolio summary."""
        return {
            "total_value": round(self.total_value, 2),
            "cash": round(self.cash, 2),
            "invested": round(self.invested, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_pct": round(self.total_pnl_pct, 2),
            "exposure_pct": round(self.exposure_pct, 2),
            "num_positions": self.num_positions,
            "holdings": {t: p.to_dict() for t, p in self.positions.items()},
            "initial_capital": self.initial_capital,
        }

    def get_sector_exposure(self) -> Dict[str, float]:
        """Calculate exposure by sector."""
        sectors = {}
        for pos in self.positions.values():
            sectors[pos.sector] = sectors.get(pos.sector, 0) + pos.value
        total = sum(sectors.values()) if sectors.values() else 1
        return {k: round(v / total * 100, 1) for k, v in sectors.items()}

    def save_state(self):
        """Save portfolio state to JSON file."""
        state = {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "positions": {t: p.to_dict() for t, p in self.positions.items()},
            "trade_history": self.trade_history[-100:],  # Keep last 100
            "last_saved": datetime.now().isoformat(),
        }
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving portfolio state: {e}")

    def load_state(self):
        """Load portfolio state from JSON file."""
        if not os.path.exists(self.state_file):
            return

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            self.initial_capital = state.get("initial_capital", self.initial_capital)
            self.cash = state.get("cash", self.initial_capital)

            for ticker, pos_data in state.get("positions", {}).items():
                self.positions[ticker] = Position(
                    ticker=ticker,
                    shares=pos_data.get("shares", 0),
                    avg_cost=pos_data.get("avg_cost", 0),
                    current_price=pos_data.get("current_price", 0),
                    sector=pos_data.get("sector", "Unknown"),
                    entry_date=pos_data.get("entry_date", ""),
                    stop_loss=pos_data.get("stop_loss", 0),
                    take_profit=pos_data.get("take_profit", 0),
                    highest_price=pos_data.get("highest_price", pos_data.get("avg_cost", 0)),
                    lowest_price=pos_data.get("lowest_price", pos_data.get("avg_cost", 0)),
                )

            self.trade_history = state.get("trade_history", [])
            logger.info(f"Loaded portfolio: ${self.total_value:,.2f} ({self.num_positions} positions)")

        except Exception as e:
            logger.error(f"Error loading portfolio state: {e}")

    def print_portfolio(self) -> str:
        """Generate a formatted portfolio report."""
        lines = [
            "=" * 60,
            "📊 PORTFOLIO SUMMARY",
            "=" * 60,
            f"Total Value:    ${self.total_value:>14,.2f}",
            f"Cash:           ${self.cash:>14,.2f}",
            f"Invested:       ${self.invested:>14,.2f}",
            f"P&L:            ${self.total_pnl:>14,.2f} ({self.total_pnl_pct:+.2f}%)",
            f"Exposure:       {self.exposure_pct:>13.1f}%",
            f"Positions:      {self.num_positions:>13d}",
            "-" * 60,
        ]

        if self.positions:
            lines.append(f"{'Ticker':<8} {'Shares':>8} {'AvgCost':>10} {'Price':>10} {'P&L%':>8} {'Value':>12}")
            lines.append("-" * 60)
            for ticker, pos in sorted(self.positions.items(), key=lambda x: x[1].value, reverse=True):
                lines.append(
                    f"{ticker:<8} {pos.shares:>8.0f} ${pos.avg_cost:>9.2f} ${pos.current_price:>9.2f} "
                    f"{pos.pnl_pct:>+7.2f}% ${pos.value:>11,.2f}"
                )

        lines.append("=" * 60)
        return "\n".join(lines)
