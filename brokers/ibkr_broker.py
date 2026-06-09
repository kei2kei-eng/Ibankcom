"""
Interactive Brokers (IBKR) Connector
====================================
Connects to Interactive Brokers via ib_insync library.

WHY IBKR?
- Most popular professional broker for algorithmic trading
- Access to 150+ markets worldwide
- Lowest margin rates
- Most advanced order types
- Professional-grade execution

REQUIREMENTS:
  1. Interactive Brokers account (https://www.interactivebrokers.com)
  2. TWS (Trader Workstation) or IB Gateway installed and running
  3. pip install ib_insync
  4. In TWS: Enable API connections (Edit → Global Configuration → API → Settings)

CONNECTION FLOW:
  ┌──────────────────────────┐
  │  Our AI System           │
  │  CEO: "BUY 100 AAPL"    │
  └────────────┬─────────────┘
               │
               │  ib_insync API call
               ▼
  ┌──────────────────────────┐
  │  TWS / IB Gateway        │    ← You run this on your computer
  │  (IB's trading software) │
  └────────────┬─────────────┘
               │
               │  Secure connection to IB servers
               ▼
  ┌──────────────────────────┐
  │  Interactive Brokers     │
  │  (brokerage server)      │
  └────────────┬─────────────┘
               │
               │  Route to exchange
               ▼
  ┌──────────────────────────┐
  │  Stock Exchange          │
  │  (NYSE / NASDAQ / etc.)  │
  └──────────────────────────┘
"""

import logging
import os
from typing import Dict, List, Optional
from .base_broker import (
    BaseBroker, OrderResult, PositionInfo, AccountInfo,
    OrderSide, OrderType, OrderStatus, TimeInForce,
)

logger = logging.getLogger(__name__)


class InteractiveBrokersConnector(BaseBroker):
    """
    Connects to Interactive Brokers via TWS or IB Gateway.
    
    SETUP:
      1. Install TWS or IB Gateway from interactivebrokers.com
      2. In TWS: Edit → Global Configuration → API → Settings
         - Enable ActiveX and Socket Clients ✓
         - Socket port: 7497 (paper) or 7496 (live)
      3. pip install ib_insync
      4. Set in .env:
           IBKR_HOST=127.0.0.1
           IBKR_PORT=7497          # 7497=paper, 7496=live
           IBKR_CLIENT_ID=1
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        client_id: int = None,
    ):
        super().__init__(name="Interactive Brokers")
        self.host = host or os.getenv("IBKR_HOST", "127.0.0.1")
        self.port = int(port or os.getenv("IBKR_PORT", "7497"))
        self.client_id = int(client_id or os.getenv("IBKR_CLIENT_ID", "1"))
        self._ib = None

        if self.port == 7497:
            self.name = "Interactive Brokers (Paper Trading)"

    def connect(self) -> bool:
        """
        Connect to TWS/IB Gateway.
        
        IMPORTANT: TWS or IB Gateway must be running on your computer!
        """
        try:
            from ib_insync import IB

            self._ib = IB()
            self._ib.connect(self.host, self.port, clientId=self.client_id)

            self.connected = True
            account = self._ib.managedAccounts()[0] if self._ib.managedAccounts() else "Unknown"

            logger.info(f"✅ IBKR connected: {self.name}")
            logger.info(f"   Host: {self.host}:{self.port}")
            logger.info(f"   Account: {account}")
            logger.info(f"   Paper: {'Yes' if self.port in (7497, 7498) else 'No'}")

            return True

        except ImportError:
            logger.error("❌ ib_insync not installed. Run: pip install ib_insync")
            return False
        except Exception as e:
            logger.error(f"❌ IBKR connection failed: {e}")
            logger.error("   Make sure TWS or IB Gateway is running!")
            logger.error(f"   Expected at {self.host}:{self.port}")
            return False

    def disconnect(self):
        if self._ib:
            self._ib.disconnect()
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected and self._ib is not None

    def get_account_info(self) -> AccountInfo:
        try:
            summary = self._ib.accountSummary()
            data = {s.tag: float(s.value) for s in summary if s.value}
            return AccountInfo(
                account_id=str(self._ib.managedAccounts()[0]) if self._ib.managedAccounts() else "",
                cash=data.get("TotalCashValue", 0),
                total_value=data.get("NetLiquidation", 0),
                buying_power=data.get("BuyingPower", 0),
                invested=data.get("GrossPositionValue", 0),
                unrealized_pnl=data.get("UnrealizedPnL", 0),
                is_paper=self.port in (7497, 7498),
                broker_name=self.name,
            )
        except Exception as e:
            logger.error(f"IBKR account error: {e}")
            return AccountInfo(is_paper=True, broker_name=self.name)

    def submit_market_order(self, ticker, shares, side,
                            time_in_force=TimeInForce.DAY) -> OrderResult:
        try:
            from ib_insync import Stock, MarketOrder

            contract = Stock(ticker, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            ib_side = "BUY" if side == OrderSide.BUY else "SELL"
            order = MarketOrder(ib_side, int(shares))

            trade = self._ib.placeOrder(contract, order)

            logger.info(f"📤 IBKR ORDER: {ib_side} {shares} {ticker} (order_id: {trade.order.orderId})")

            return OrderResult(
                success=True,
                order_id=str(trade.order.orderId),
                status=OrderStatus.SUBMITTED,
                ticker=ticker,
                side=side,
                order_type=OrderType.MARKET,
                shares=shares,
                message=f"Order submitted to IBKR: {trade.order.orderId}",
            )

        except Exception as e:
            logger.error(f"IBKR order error: {e}")
            return OrderResult(success=False, ticker=ticker, side=side, message=str(e))

    def submit_limit_order(self, ticker, shares, side, limit_price,
                           time_in_force=TimeInForce.DAY) -> OrderResult:
        try:
            from ib_insync import Stock, LimitOrder

            contract = Stock(ticker, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            ib_side = "BUY" if side == OrderSide.BUY else "SELL"
            order = LimitOrder(ib_side, int(shares), limit_price)
            trade = self._ib.placeOrder(contract, order)

            return OrderResult(
                success=True, order_id=str(trade.order.orderId),
                ticker=ticker, side=side,
                order_type=OrderType.LIMIT,
                shares=shares, price=limit_price,
            )
        except Exception as e:
            return OrderResult(success=False, ticker=ticker, message=str(e))

    def submit_stop_order(self, ticker, shares, side, stop_price,
                          time_in_force=TimeInForce.GTC) -> OrderResult:
        try:
            from ib_insync import Stock, StopOrder

            contract = Stock(ticker, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            ib_side = "BUY" if side == OrderSide.BUY else "SELL"
            order = StopOrder(ib_side, int(shares), stop_price)
            trade = self._ib.placeOrder(contract, order)

            return OrderResult(
                success=True, order_id=str(trade.order.orderId),
                ticker=ticker, side=side,
                order_type=OrderType.STOP,
                shares=shares, price=stop_price,
            )
        except Exception as e:
            return OrderResult(success=False, ticker=ticker, message=str(e))

    def submit_bracket_order(self, ticker, shares, side,
                             take_profit_price, stop_loss_price) -> OrderResult:
        try:
            from ib_insync import Stock

            contract = Stock(ticker, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            ib_side = "BUY" if side == OrderSide.BUY else "SELL"
            bracket = self._ib.bracketOrder(
                ib_side, int(shares),
                limitPrice=0,  # Market for entry
                takeProfitPrice=take_profit_price,
                stopLossPrice=stop_loss_price,
            )

            for order in bracket:
                self._ib.placeOrder(contract, order)

            logger.info(f"📤 IBKR BRACKET: {ib_side} {shares} {ticker} "
                       f"TP=${take_profit_price:.2f} SL=${stop_loss_price:.2f}")

            return OrderResult(
                success=True,
                order_id=str(bracket[0].orderId),
                ticker=ticker, side=side,
                shares=shares,
                message=f"Bracket order: TP=${take_profit_price:.2f}, SL=${stop_loss_price:.2f}",
            )

        except Exception as e:
            logger.error(f"IBKR bracket error: {e}")
            return self.submit_market_order(ticker, shares, side)

    def cancel_order(self, order_id: str) -> bool:
        try:
            trades = self._ib.openTrades()
            for trade in trades:
                if str(trade.order.orderId) == order_id:
                    self._ib.cancelOrder(trade.order)
                    return True
            return False
        except Exception as e:
            logger.error(f"Cancel error: {e}")
            return False

    def get_order_status(self, order_id: str) -> OrderResult:
        return OrderResult(success=False, order_id=order_id, message="Use IB event callbacks instead")

    def get_positions(self) -> List[PositionInfo]:
        try:
            positions = self._ib.positions()
            result = []
            for pos in positions:
                result.append(PositionInfo(
                    ticker=pos.contract.symbol,
                    shares=float(pos.position),
                    avg_entry_price=float(pos.avgCost),
                    current_price=0,  # Would need to fetch separately
                    market_value=float(pos.position * pos.avgCost),
                    unrealized_pnl=0,
                    unrealized_pnl_pct=0,
                ))
            return result
        except Exception as e:
            logger.error(f"IBKR positions error: {e}")
            return []

    def get_position(self, ticker: str) -> Optional[PositionInfo]:
        positions = self.get_positions()
        for pos in positions:
            if pos.ticker == ticker:
                return pos
        return None

    def close_position(self, ticker: str, pct: float = 100.0) -> OrderResult:
        pos = self.get_position(ticker)
        if not pos:
            return OrderResult(success=False, ticker=ticker, message="No position")
        shares = pos.shares * (pct / 100)
        return self.submit_market_order(ticker, shares, OrderSide.SELL)

    def get_current_price(self, ticker: str) -> float:
        try:
            from ib_insync import Stock
            contract = Stock(ticker, "SMART", "USD")
            self._ib.qualifyContracts(contract)
            ticker_obj = self._ib.reqMktData(contract, "", True, False)
            self._ib.sleep(2)  # Wait for data
            price = ticker_obj.marketPrice()
            return float(price) if price else 0.0
        except Exception:
            return 0.0

    def is_market_open(self) -> bool:
        try:
            from ib_insync import Stock
            contract = Stock("SPY", "SMART", "USD")
            details = self._ib.reqDetails(contract)
            # Simplified check
            return True  # Would need proper session check
        except Exception:
            return False
