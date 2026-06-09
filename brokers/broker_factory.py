"""
Broker Factory
==============
Creates the right broker based on configuration.
This is what you call to connect to a real brokerage.
"""

import os
import logging
from typing import Optional
from .base_broker import BaseBroker
from .paper_broker import PaperBroker
from .alpaca_broker import AlpacaBroker
from .ibkr_broker import InteractiveBrokersConnector

logger = logging.getLogger(__name__)


def create_broker(
    broker_name: str = None,
    initial_capital: float = 1_000_000,
) -> BaseBroker:
    """
    Create and connect to the specified broker.
    
    Args:
        broker_name: "paper", "alpaca", or "ibkr"
            If None, reads from .env BROKER_TYPE, defaults to "paper"
        initial_capital: Starting capital (only used for paper trading)
    
    Returns:
        Connected BaseBroker instance
    
    Example:
        # Paper trading (default, no setup needed)
        broker = create_broker("paper")
        
        # Alpaca (free paper account at alpaca.markets)
        broker = create_broker("alpaca")
        
        # Interactive Brokers (professional)
        broker = create_broker("ibkr")
    """
    # Determine broker type
    broker_name = (
        broker_name
        or os.getenv("BROKER_TYPE", "paper")
    ).lower().strip()

    logger.info(f"🔌 Creating broker: {broker_name}")

    # ── Paper Trading ──
    if broker_name == "paper":
        broker = PaperBroker(initial_capital=initial_capital)
        broker.connect()
        return broker

    # ── Alpaca ──
    elif broker_name == "alpaca":
        paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"
        broker = AlpacaBroker(paper=paper)
        if broker.connect():
            return broker
        else:
            logger.warning("⚠️  Alpaca connection failed. Falling back to paper trading.")
            return create_broker("paper", initial_capital)

    # ── Interactive Brokers ──
    elif broker_name in ("ibkr", "interactive_brokers", "ib"):
        broker = InteractiveBrokersConnector()
        if broker.connect():
            return broker
        else:
            logger.warning("⚠️  IBKR connection failed. Falling back to paper trading.")
            return create_broker("paper", initial_capital)

    else:
        logger.error(f"Unknown broker: {broker_name}. Use 'paper', 'alpaca', or 'ibkr'.")
        return create_broker("paper", initial_capital)


def list_available_brokers():
    """Print info about all supported brokers."""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║           🏦 SUPPORTED BROKER CONNECTIONS                         ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  1. 📝 PAPER TRADING (Default)                                    ║
║     • Built-in simulation, no setup needed                         ║
║     • No real money                                                ║
║     • Use: create_broker("paper")                                  ║
║                                                                    ║
║  2. 🦙 ALPACA (Recommended for beginners)                         ║
║     • Free paper trading account                                   ║
║     • Commission-free real trading                                 ║
║     • Simple REST API                                              ║
║     • Sign up: https://app.alpaca.markets/signup                  ║
║     • Install: pip install alpaca-py                               ║
║     • .env: ALPACA_API_KEY=PKZ...                                 ║
║             ALPACA_SECRET_KEY=wzR...                               ║
║             ALPACA_PAPER=true                                      ║
║     • Use: create_broker("alpaca")                                 ║
║                                                                    ║
║  3. 🏢 INTERACTIVE BROKERS (Professional)                         ║
║     • Most popular for algorithmic trading                         ║
║     • Access to 150+ global markets                                ║
║     • Lowest margin rates                                          ║
║     • Requires TWS or IB Gateway running                           ║
║     • Sign up: https://www.interactivebrokers.com                 ║
║     • Install: pip install ib_insync                               ║
║     • .env: IBKR_HOST=127.0.0.1                                   ║
║             IBKR_PORT=7497                                         ║
║             IBKR_CLIENT_ID=1                                       ║
║     • Use: create_broker("ibkr")                                   ║
║                                                                    ║
╠══════════════════════════════════════════════════════════════════════╣
║  CONNECTION FLOW:                                                  ║
║                                                                    ║
║  AI System → Broker Connector → Broker Server → Stock Exchange    ║
║                                                                    ║
║  Example with Alpaca:                                             ║
║  ┌──────────────┐   HTTPS REST   ┌──────────┐   route   ┌──────┐ ║
║  │ Our AI Trade │ ─────────────→ │ Alpaca   │ ────────→ │ NYSE │ ║
║  │ System       │ ←───────────── │ Server   │ ←──────── │      │ ║
║  └──────────────┘   JSON response └──────────┘   fill    └──────┘ ║
║                                                                    ║
╚══════════════════════════════════════════════════════════════════════╝
""")
