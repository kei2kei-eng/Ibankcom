"""
Broker Connectors — Link AI iBank to Real Securities Firms
============================================================

This is the bridge between the AI trading system and real brokerages.

Architecture:
  ┌───────────────────────────────────────────────────┐
  │             AI Investment Bank (our system)        │
  │   CEO decides: BUY 100 AAPL @ market              │
  └───────────────────┬───────────────────────────────┘
                      │
              ┌───────▼────────┐
              │  Broker Base   │  Abstract interface
              │  (this file)   │
              └───────┬────────┘
                      │
        ┌─────────────┼──────────────┐
        │             │              │
  ┌─────▼────┐  ┌─────▼────┐  ┌─────▼────┐
  │  Alpaca   │  │ IBKR     │  │  Paper   │
  │  Broker   │  │ (Inter.  │  │  Trading │
  │  (easy)   │  │  Brokers)│  │  (sim)   │
  └───────────┘  └──────────┘  └──────────┘

Supported Brokers:
  - Alpaca (https://alpaca.markets) — Easiest, free paper trading, REST API
  - Interactive Brokers (IBKR) — Professional, TWS/IB Gateway needed
  - Paper Trading — Built-in simulation (default)

How to connect to a real broker:
  1. Create an account at the brokerage
  2. Get API keys
  3. Set keys in .env file
  4. Run: python main.py --broker alpaca --mode auto
"""

from .base_broker import BaseBroker, OrderResult, PositionInfo, AccountInfo
from .paper_broker import PaperBroker
from .alpaca_broker import AlpacaBroker
from .ibkr_broker import InteractiveBrokersConnector
from .broker_factory import create_broker

__all__ = [
    "BaseBroker", "OrderResult", "PositionInfo", "AccountInfo",
    "PaperBroker", "AlpacaBroker", "InteractiveBrokersConnector",
    "create_broker",
]
