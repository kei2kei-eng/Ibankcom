"""
Base Broker Interface
=====================
Defines the standard interface that ALL broker connectors must implement.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum


logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"          # Execute immediately at current price
    LIMIT = "limit"            # Execute only at specified price or better
    STOP = "stop"              # Market order triggered at stop price
    STOP_LIMIT = "stop_limit"  # Limit order triggered at stop price
    TRAILING_STOP = "trailing_stop"  # Stop that follows price


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class TimeInForce(Enum):
    DAY = "day"                # Good for the trading day
    GTC = "gtc"                # Good till cancelled
    IOC = "ioc"                # Immediate or cancel
    OPG = "opg"                # At market open


@dataclass
class OrderResult:
    """Result of placing an order."""
    success: bool
    order_id: str = ""
    status: OrderStatus = OrderStatus.PENDING
    ticker: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    shares: float = 0
    price: float = 0.0
    filled_price: float = 0.0     # Actual execution price
    filled_shares: float = 0.0    # Actually filled quantity
    timestamp: str = ""
    commission: float = 0.0
    message: str = ""
    raw_response: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "order_id": self.order_id,
            "status": self.status.value,
            "ticker": self.ticker,
            "side": self.side.value,
            "shares": self.shares,
            "price": self.price,
            "filled_price": self.filled_price,
            "filled_shares": self.filled_shares,
            "commission": self.commission,
            "message": self.message,
        }


@dataclass
class PositionInfo:
    """Information about a position at the broker."""
    ticker: str
    shares: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float

    def to_dict(self) -> Dict:
        return {
            "ticker": self.ticker,
            "shares": self.shares,
            "avg_entry_price": self.avg_entry_price,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 2),
        }


@dataclass
class AccountInfo:
    """Information about the brokerage account."""
    account_id: str = ""
    cash: float = 0.0
    total_value: float = 0.0
    buying_power: float = 0.0
    invested: float = 0.0
    unrealized_pnl: float = 0.0
    currency: str = "USD"
    is_paper: bool = True
    broker_name: str = ""

    def to_dict(self) -> Dict:
        return {
            "account_id": self.account_id,
            "cash": round(self.cash, 2),
            "total_value": round(self.total_value, 2),
            "buying_power": round(self.buying_power, 2),
            "invested": round(self.invested, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "is_paper": self.is_paper,
            "broker_name": self.broker_name,
        }


class BaseBroker(ABC):
    """
    Abstract base class for all broker connectors.
    
    Every broker (Alpaca, IBKR, etc.) must implement these methods.
    The AI trading system ONLY talks to this interface — it never
    directly calls broker-specific APIs.
    """

    def __init__(self, name: str):
        self.name = name
        self.connected = False

    # ──────────────────────────────────────────────
    # CONNECTION
    # ──────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """
        Connect to the broker's API.
        Returns True if connection successful.
        """
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the broker."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if currently connected."""
        pass

    # ──────────────────────────────────────────────
    # ACCOUNT
    # ──────────────────────────────────────────────

    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """Get account details (cash, buying power, etc.)."""
        pass

    # ──────────────────────────────────────────────
    # TRADING
    # ──────────────────────────────────────────────

    @abstractmethod
    def submit_market_order(
        self,
        ticker: str,
        shares: float,
        side: OrderSide,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> OrderResult:
        """
        Submit a MARKET order (execute immediately at current price).
        This is the most common order type for AI trading.
        """
        pass

    @abstractmethod
    def submit_limit_order(
        self,
        ticker: str,
        shares: float,
        side: OrderSide,
        limit_price: float,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> OrderResult:
        """Submit a LIMIT order (execute only at specified price or better)."""
        pass

    @abstractmethod
    def submit_stop_order(
        self,
        ticker: str,
        shares: float,
        side: OrderSide,
        stop_price: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> OrderResult:
        """
        Submit a STOP order (becomes market order when price hits stop).
        Used for STOP-LOSS orders.
        """
        pass

    @abstractmethod
    def submit_bracket_order(
        self,
        ticker: str,
        shares: float,
        side: OrderSide,
        take_profit_price: float,
        stop_loss_price: float,
    ) -> OrderResult:
        """
        Submit a BRACKET order: main order + take-profit + stop-loss.
        This is the BEST order type for automated trading because
        it automatically sets exit conditions.
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderResult:
        """Get the current status of an order."""
        pass

    # ──────────────────────────────────────────────
    # POSITIONS
    # ──────────────────────────────────────────────

    @abstractmethod
    def get_positions(self) -> List[PositionInfo]:
        """Get all current positions."""
        pass

    @abstractmethod
    def get_position(self, ticker: str) -> Optional[PositionInfo]:
        """Get position for a specific ticker."""
        pass

    @abstractmethod
    def close_position(self, ticker: str, pct: float = 100.0) -> OrderResult:
        """Close a position (sell all or a percentage)."""
        pass

    # ──────────────────────────────────────────────
    # MARKET DATA (some brokers provide this too)
    # ──────────────────────────────────────────────

    @abstractmethod
    def get_current_price(self, ticker: str) -> float:
        """Get the current real-time price from the broker."""
        pass

    @abstractmethod
    def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        pass

    # ──────────────────────────────────────────────
    # UTILITY
    # ──────────────────────────────────────────────

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name} (connected={self.connected})>"
