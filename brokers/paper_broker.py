"""
Paper Trading Broker (Built-in Simulation)
==========================================
The default broker — simulates all trades without real money.
This is what the system uses when no real broker is connected.
"""

import logging
import uuid
from typing import Dict, List, Optional
from datetime import datetime
from .base_broker import (
    BaseBroker, OrderResult, PositionInfo, AccountInfo,
    OrderSide, OrderType, OrderStatus, TimeInForce,
)

logger = logging.getLogger(__name__)


class PaperBroker(BaseBroker):
    """
    Paper trading broker — simulates everything locally.
    No real money, no API keys needed.
    """

    def __init__(self, initial_capital: float = 1_000_000):
        super().__init__(name="Paper Trading")
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Dict] = {}  # ticker → {shares, avg_cost, current_price, ...}
        self.orders: Dict[str, Dict] = {}
        self.commission_per_trade = 0.0  # Paper trading is free

    def connect(self) -> bool:
        self.connected = True
        logger.info(f"📝 Paper Broker connected (capital: ${self.cash:,.2f})")
        return True

    def disconnect(self):
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def get_account_info(self) -> AccountInfo:
        invested = sum(
            p["shares"] * p["current_price"]
            for p in self.positions.values()
        )
        total_value = self.cash + invested
        unrealized_pnl = sum(
            (p["current_price"] - p["avg_cost"]) * p["shares"]
            for p in self.positions.values()
        )
        return AccountInfo(
            account_id="PAPER-001",
            cash=self.cash,
            total_value=total_value,
            buying_power=self.cash,  # No margin in paper trading
            invested=invested,
            unrealized_pnl=unrealized_pnl,
            is_paper=True,
            broker_name="Paper Trading (Simulation)",
        )

    def submit_market_order(
        self, ticker: str, shares: float, side: OrderSide,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> OrderResult:
        """Simulate a market order — executes immediately at 'current price'."""
        # In paper trading, we need a price source
        price = self._get_simulated_price(ticker)
        if price <= 0:
            return OrderResult(
                success=False, ticker=ticker, side=side,
                message=f"Cannot get price for {ticker}",
            )

        order_id = f"PAPER-{uuid.uuid4().hex[:8]}"

        if side == OrderSide.BUY:
            cost = shares * price
            if cost > self.cash:
                shares = int(self.cash / price)
                if shares <= 0:
                    return OrderResult(
                        success=False, order_id=order_id,
                        ticker=ticker, side=side,
                        message="Insufficient cash",
                    )
                cost = shares * price

            self.cash -= cost

            if ticker in self.positions:
                pos = self.positions[ticker]
                total_cost = pos["avg_cost"] * pos["shares"] + cost
                total_shares = pos["shares"] + shares
                pos["avg_cost"] = total_cost / total_shares
                pos["shares"] = total_shares
                pos["current_price"] = price
            else:
                self.positions[ticker] = {
                    "shares": shares,
                    "avg_cost": price,
                    "current_price": price,
                }

            logger.info(f"📝 PAPER BUY: {shares} {ticker} @ ${price:.2f} = ${shares * price:,.2f}")

        elif side == OrderSide.SELL:
            if ticker not in self.positions or self.positions[ticker]["shares"] <= 0:
                return OrderResult(
                    success=False, order_id=order_id,
                    ticker=ticker, side=side,
                    message="No position to sell",
                )

            pos = self.positions[ticker]
            shares = min(shares, pos["shares"])
            proceeds = shares * price

            self.cash += proceeds
            pos["shares"] -= shares
            pos["current_price"] = price

            if pos["shares"] <= 0:
                del self.positions[ticker]

            logger.info(f"📝 PAPER SELL: {shares} {ticker} @ ${price:.2f} = ${proceeds:,.2f}")

        result = OrderResult(
            success=True,
            order_id=order_id,
            status=OrderStatus.FILLED,
            ticker=ticker,
            side=side,
            order_type=OrderType.MARKET,
            shares=shares,
            price=price,
            filled_price=price,
            filled_shares=shares,
            timestamp=datetime.now().isoformat(),
            commission=0.0,
            message=f"Paper trade filled: {side.value} {shares} {ticker} @ ${price:.2f}",
        )

        self.orders[order_id] = result.to_dict()
        return result

    def submit_limit_order(self, ticker, shares, side, limit_price,
                           time_in_force=TimeInForce.DAY) -> OrderResult:
        """In paper trading, we simulate limit orders as immediate fills for simplicity."""
        logger.info(f"📝 PAPER LIMIT: {side.value} {shares} {ticker} @ ${limit_price:.2f} (simulated as market)")
        return self.submit_market_order(ticker, shares, side, time_in_force)

    def submit_stop_order(self, ticker, shares, side, stop_price,
                          time_in_force=TimeInForce.GTC) -> OrderResult:
        """Simulate a stop order."""
        logger.info(f"📝 PAPER STOP: {side.value} {shares} {ticker} stop @ ${stop_price:.2f}")
        return OrderResult(
            success=True, order_id=f"PAPER-STOP-{uuid.uuid4().hex[:8]}",
            status=OrderStatus.SUBMITTED, ticker=ticker, side=side,
            order_type=OrderType.STOP, shares=shares, price=stop_price,
            message="Stop order placed (paper)",
        )

    def submit_bracket_order(self, ticker, shares, side,
                             take_profit_price, stop_loss_price) -> OrderResult:
        """Simulate a bracket order (main + TP + SL)."""
        # Execute main order
        main_order = self.submit_market_order(ticker, shares, side)
        if main_order.success:
            main_order.message += (
                f" | Bracket: TP=${take_profit_price:.2f}, SL=${stop_loss_price:.2f} "
                f"(will be monitored by system)"
            )
        return main_order

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self.orders:
            self.orders[order_id]["status"] = OrderStatus.CANCELLED.value
            return True
        return False

    def get_order_status(self, order_id: str) -> OrderResult:
        if order_id in self.orders:
            d = self.orders[order_id]
            return OrderResult(
                success=True, order_id=order_id,
                status=OrderStatus(d.get("status", "filled")),
                ticker=d.get("ticker", ""),
                message=d.get("message", ""),
            )
        return OrderResult(success=False, order_id=order_id, message="Order not found")

    def get_positions(self) -> List[PositionInfo]:
        positions = []
        for ticker, pos in self.positions.items():
            positions.append(PositionInfo(
                ticker=ticker,
                shares=pos["shares"],
                avg_entry_price=pos["avg_cost"],
                current_price=pos["current_price"],
                market_value=pos["shares"] * pos["current_price"],
                unrealized_pnl=(pos["current_price"] - pos["avg_cost"]) * pos["shares"],
                unrealized_pnl_pct=((pos["current_price"] - pos["avg_cost"]) / pos["avg_cost"] * 100)
                if pos["avg_cost"] > 0 else 0,
            ))
        return positions

    def get_position(self, ticker: str) -> Optional[PositionInfo]:
        if ticker not in self.positions:
            return None
        pos = self.positions[ticker]
        return PositionInfo(
            ticker=ticker,
            shares=pos["shares"],
            avg_entry_price=pos["avg_cost"],
            current_price=pos["current_price"],
            market_value=pos["shares"] * pos["current_price"],
            unrealized_pnl=(pos["current_price"] - pos["avg_cost"]) * pos["shares"],
            unrealized_pnl_pct=((pos["current_price"] - pos["avg_cost"]) / pos["avg_cost"] * 100)
            if pos["avg_cost"] > 0 else 0,
        )

    def close_position(self, ticker: str, pct: float = 100.0) -> OrderResult:
        if ticker not in self.positions:
            return OrderResult(success=False, ticker=ticker, message="No position")
        pos = self.positions[ticker]
        shares_to_sell = pos["shares"] * (pct / 100)
        return self.submit_market_order(ticker, shares_to_sell, OrderSide.SELL)

    def get_current_price(self, ticker: str) -> float:
        return self._get_simulated_price(ticker)

    def is_market_open(self) -> bool:
        """Simple check: US market hours 9:30-16:00 ET."""
        from datetime import timezone, timedelta
        now = datetime.now(timezone(timedelta(hours=-4)))  # ET
        if now.weekday() >= 5:
            return False
        return 9 <= now.hour < 16  # Rough check

    def update_prices(self, prices: Dict[str, float]):
        """Update position prices from market data."""
        for ticker, price in prices.items():
            if ticker in self.positions:
                self.positions[ticker]["current_price"] = price

    def _get_simulated_price(self, ticker: str) -> float:
        """Get price from the positions dict or fetch from yfinance."""
        if ticker in self.positions:
            return self.positions[ticker]["current_price"]

        # Fetch from yfinance
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                # Cache it as a zero-share position for future lookups
                self.positions[ticker] = {
                    "shares": 0,
                    "avg_cost": price,
                    "current_price": price,
                }
                return price
        except Exception as e:
            logger.debug(f"Price fetch failed for {ticker}: {e}")
        return 0.0
