"""
Alpaca Broker Connector
=======================
Connects to Alpaca Markets (https://alpaca.markets)

WHY ALPACA?
- Free paper trading account (no money needed to test)
- Commission-free trading
- Simple REST API — perfect for algorithmic trading
- Supports stocks and crypto
- Bracket orders, trailing stops built-in
- Real-time data via WebSocket

SETUP:
  1. Go to https://app.alpaca.markets/signup
  2. Create a FREE account
  3. Go to API Keys page
  4. Copy your API Key and Secret
  5. Set in .env:
       ALPACA_API_KEY=PKZ...
       ALPACA_SECRET_KEY=wzR...
       ALPACA_PAPER=true          # true = paper trading, false = real money
  6. pip install alpaca-py

CONNECTION FLOW:
  ┌──────────────────────────┐
  │  Our AI System           │
  │  CEO: "BUY 100 AAPL"    │
  └────────────┬─────────────┘
               │
               │  Python API call
               ▼
  ┌──────────────────────────┐
  │  alpaca-py library       │
  │  (our connector)         │
  └────────────┬─────────────┘
               │
               │  HTTPS REST API
               ▼
  ┌──────────────────────────┐
  │  Alpaca Markets Server   │
  │  (brokerage backend)     │
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
from datetime import datetime
from .base_broker import (
    BaseBroker, OrderResult, PositionInfo, AccountInfo,
    OrderSide, OrderType, OrderStatus, TimeInForce,
)

logger = logging.getLogger(__name__)


class AlpacaBroker(BaseBroker):
    """
    Real broker connector for Alpaca Markets.
    
    Install: pip install alpaca-py
    Docs: https://docs.alpaca.markets/docs/about-market-data-api
    """

    def __init__(
        self,
        api_key: str = None,
        secret_key: str = None,
        paper: bool = True,
    ):
        super().__init__(name="Alpaca")
        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY", "")
        self.paper = paper
        self._trading_client = None
        self._stock_client = None

        if self.paper:
            self.name = "Alpaca (Paper Trading)"

    def connect(self) -> bool:
        """
        Connect to Alpaca's API using alpaca-py.
        
        What happens:
          1. Create TradingClient with API keys
          2. Test connection by fetching account info
          3. If successful → connected = True
        """
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.stock.client import StockHistoricalDataClient

            # Create trading client (paper or live)
            self._trading_client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper,  # True = paper trading server
            )

            # Create data client for price info
            self._stock_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
            )

            # Test connection: get account
            account = self._trading_client.get_account()
            self.connected = True

            logger.info(f"✅ Alpaca connected: {self.name}")
            logger.info(f"   Account: {account.account_number}")
            logger.info(f"   Cash: ${float(account.cash):,.2f}")
            logger.info(f"   Buying Power: ${float(account.buying_power):,.2f}")
            logger.info(f"   Paper Trading: {self.paper}")

            return True

        except ImportError:
            logger.error("❌ alpaca-py not installed. Run: pip install alpaca-py")
            return False
        except Exception as e:
            logger.error(f"❌ Alpaca connection failed: {e}")
            logger.error("   Check your API keys in .env (ALPACA_API_KEY, ALPACA_SECRET_KEY)")
            self.connected = False
            return False

    def disconnect(self):
        self._trading_client = None
        self._stock_client = None
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    # ── Account ──

    def get_account_info(self) -> AccountInfo:
        try:
            acc = self._trading_client.get_account()
            return AccountInfo(
                account_id=acc.account_number,
                cash=float(acc.cash),
                total_value=float(acc.portfolio_value),
                buying_power=float(acc.buying_power),
                invested=float(acc.long_market_value),
                unrealized_pnl=float(acc.unrealized_pl),
                is_paper=self.paper,
                broker_name=self.name,
            )
        except Exception as e:
            logger.error(f"Error getting account: {e}")
            return AccountInfo(is_paper=self.paper, broker_name=self.name)

    # ── Orders ──

    def submit_market_order(self, ticker, shares, side,
                            time_in_force=TimeInForce.DAY) -> OrderResult:
        """
        Submit a market order to Alpaca.
        
        What happens:
          1. We create a MarketOrderRequest
          2. Send it to Alpaca via REST API
          3. Alpaca routes it to the exchange
          4. Exchange fills the order
          5. Alpaca returns the fill confirmation
        """
        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce as AlpacaTIF

            alpaca_side = AlpacaSide.BUY if side == OrderSide.BUY else AlpacaSide.SELL
            alpaca_tif = AlpacaTIF.DAY if time_in_force == TimeInForce.DAY else AlpacaTIF.GTC

            request = MarketOrderRequest(
                symbol=ticker,
                qty=int(shares),
                side=alpaca_side,
                time_in_force=alpaca_tif,
            )

            order = self._trading_client.submit_order(request)

            logger.info(f"📤 Alpaca ORDER: {side.value} {shares} {ticker} "
                       f"(order_id: {order.id}, status: {order.status})")

            return OrderResult(
                success=True,
                order_id=str(order.id),
                status=self._map_status(order.status),
                ticker=ticker,
                side=side,
                order_type=OrderType.MARKET,
                shares=shares,
                price=float(order.limit_price or 0),
                filled_price=float(order.filled_avg_price or 0),
                filled_shares=float(order.filled_qty or 0),
                timestamp=str(order.submitted_at),
                commission=0.0,  # Alpaca is commission-free
                message=f"Order submitted to Alpaca: {order.id}",
                raw_response=str(order),
            )

        except Exception as e:
            logger.error(f"Alpaca order error: {e}")
            return OrderResult(
                success=False, ticker=ticker, side=side,
                message=f"Alpaca error: {e}",
            )

    def submit_limit_order(self, ticker, shares, side, limit_price,
                           time_in_force=TimeInForce.DAY) -> OrderResult:
        try:
            from alpaca.trading.requests import LimitOrderRequest
            from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce as AlpacaTIF

            alpaca_side = AlpacaSide.BUY if side == OrderSide.BUY else AlpacaSide.SELL
            alpaca_tif = AlpacaTIF.DAY if time_in_force == TimeInForce.DAY else AlpacaTIF.GTC

            request = LimitOrderRequest(
                symbol=ticker,
                qty=int(shares),
                side=alpaca_side,
                time_in_force=alpaca_tif,
                limit_price=limit_price,
            )

            order = self._trading_client.submit_order(request)

            return OrderResult(
                success=True, order_id=str(order.id),
                status=self._map_status(order.status),
                ticker=ticker, side=side,
                order_type=OrderType.LIMIT,
                shares=shares, price=limit_price,
                message=f"Limit order submitted: {order.id}",
            )

        except Exception as e:
            return OrderResult(success=False, ticker=ticker, message=str(e))

    def submit_stop_order(self, ticker, shares, side, stop_price,
                          time_in_force=TimeInForce.GTC) -> OrderResult:
        try:
            from alpaca.trading.requests import StopOrderRequest
            from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce as AlpacaTIF

            alpaca_side = AlpacaSide.BUY if side == OrderSide.BUY else AlpacaSide.SELL

            request = StopOrderRequest(
                symbol=ticker,
                qty=int(shares),
                side=alpaca_side,
                time_in_force=AlpacaTIF.GTC,
                stop_price=stop_price,
            )

            order = self._trading_client.submit_order(request)

            return OrderResult(
                success=True, order_id=str(order.id),
                ticker=ticker, side=side,
                order_type=OrderType.STOP,
                shares=shares, price=stop_price,
                message=f"Stop order submitted: {order.id}",
            )

        except Exception as e:
            return OrderResult(success=False, ticker=ticker, message=str(e))

    def submit_bracket_order(self, ticker, shares, side,
                             take_profit_price, stop_loss_price) -> OrderResult:
        """
        Bracket order = Main order + Take Profit + Stop Loss
        
        This is the BEST order type for automated trading because:
        - If price goes UP → take-profit automatically sells
        - If price goes DOWN → stop-loss automatically sells
        - No manual monitoring needed!
        """
        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.requests import TakeProfitRequest, StopLossRequest
            from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce as AlpacaTIF

            alpaca_side = AlpacaSide.BUY if side == OrderSide.BUY else AlpacaSide.SELL

            request = MarketOrderRequest(
                symbol=ticker,
                qty=int(shares),
                side=alpaca_side,
                time_in_force=AlpacaTIF.DAY,
                order_class="bracket",
                take_profit=TakeProfitRequest(limit_price=take_profit_price),
                stop_loss=StopLossRequest(stop_price=stop_loss_price),
            )

            order = self._trading_client.submit_order(request)

            logger.info(f"📤 Alpaca BRACKET: {side.value} {shares} {ticker} "
                       f"TP=${take_profit_price:.2f} SL=${stop_loss_price:.2f}")

            return OrderResult(
                success=True, order_id=str(order.id),
                status=self._map_status(order.status),
                ticker=ticker, side=side,
                order_type=OrderType.MARKET,
                shares=shares,
                message=f"Bracket order: main+TP(${take_profit_price:.2f})+SL(${stop_loss_price:.2f})",
            )

        except Exception as e:
            logger.error(f"Bracket order error: {e}")
            # Fallback: submit regular market order
            logger.info(f"Falling back to simple market order...")
            return self.submit_market_order(ticker, shares, side)

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._trading_client.cancel_order_by_id(order_id)
            return True
        except Exception as e:
            logger.error(f"Cancel error: {e}")
            return False

    def get_order_status(self, order_id: str) -> OrderResult:
        try:
            order = self._trading_client.get_order_by_id(order_id)
            return OrderResult(
                success=True, order_id=str(order.id),
                status=self._map_status(order.status),
                ticker=order.symbol,
                filled_price=float(order.filled_avg_price or 0),
                filled_shares=float(order.filled_qty or 0),
            )
        except Exception as e:
            return OrderResult(success=False, order_id=order_id, message=str(e))

    # ── Positions ──

    def get_positions(self) -> List[PositionInfo]:
        try:
            positions = self._trading_client.get_all_positions()
            result = []
            for pos in positions:
                result.append(PositionInfo(
                    ticker=pos.symbol,
                    shares=float(pos.qty),
                    avg_entry_price=float(pos.avg_entry_price),
                    current_price=float(pos.current_price),
                    market_value=float(pos.market_value),
                    unrealized_pnl=float(pos.unrealized_pl),
                    unrealized_pnl_pct=float(pos.unrealized_plpc) * 100,
                ))
            return result
        except Exception as e:
            logger.error(f"Get positions error: {e}")
            return []

    def get_position(self, ticker: str) -> Optional[PositionInfo]:
        try:
            pos = self._trading_client.get_open_position(ticker)
            return PositionInfo(
                ticker=pos.symbol,
                shares=float(pos.qty),
                avg_entry_price=float(pos.avg_entry_price),
                current_price=float(pos.current_price),
                market_value=float(pos.market_value),
                unrealized_pnl=float(pos.unrealized_pl),
                unrealized_pnl_pct=float(pos.unrealized_plpc) * 100,
            )
        except Exception:
            return None

    def close_position(self, ticker: str, pct: float = 100.0) -> OrderResult:
        try:
            self._trading_client.close_position(ticker, close_options={"percentage": str(pct)})
            return OrderResult(
                success=True, ticker=ticker,
                message=f"Closed {pct}% of {ticker} position",
            )
        except Exception as e:
            return OrderResult(success=False, ticker=ticker, message=str(e))

    # ── Market Data ──

    def get_current_price(self, ticker: str) -> float:
        try:
            from alpaca.data.requests import StockLatestTradeRequest
            request = StockLatestTradeRequest(symbol_or_symbols=ticker)
            trade = self._stock_client.get_stock_latest_trade(request)
            if ticker in trade:
                return float(trade[ticker].price)
        except Exception:
            pass

        # Fallback: yfinance
        try:
            import yfinance as yf
            return float(yf.Ticker(ticker).fast_info["lastPrice"])
        except Exception:
            return 0.0

    def is_market_open(self) -> bool:
        try:
            clock = self._trading_client.get_clock()
            return clock.is_open
        except Exception:
            return False

    # ── Helpers ──

    def _map_status(self, alpaca_status) -> OrderStatus:
        mapping = {
            "new": OrderStatus.SUBMITTED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "filled": OrderStatus.FILLED,
            "done_for_day": OrderStatus.PENDING,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
            "replaced": OrderStatus.SUBMITTED,
            "pending_cancel": OrderStatus.CANCELLED,
            "pending_replace": OrderStatus.PENDING,
            "accepted": OrderStatus.SUBMITTED,
            "pending_new": OrderStatus.PENDING,
            "accepted_for_bidding": OrderStatus.SUBMITTED,
            "stopped": OrderStatus.SUBMITTED,
            "rejected": OrderStatus.REJECTED,
            "suspended": OrderStatus.PENDING,
            "calculated": OrderStatus.SUBMITTED,
        }
        status_str = str(alpaca_status).split(".")[-1].lower() if alpaca_status else "pending"
        return mapping.get(status_str, OrderStatus.PENDING)
