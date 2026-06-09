#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# 🦞 AI iBank — Quick Setup Script
# ═══════════════════════════════════════════════════════════════
# 
# This script helps you connect your existing OpenAI account
# to the AI Investment Bank Trading System.
#
# PREREQUISITE: You need an OpenAI API key
#   Get one at: https://platform.openai.com/api-keys
#   (Use the same key you use for ChatGPT API)
#
# ═══════════════════════════════════════════════════════════════

set -e

echo ""
echo "🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞"
echo "🏦 AI Investment Bank — Setup Wizard"
echo "🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞"
echo ""

# ── Step 1: Check Python ──
echo "📋 Step 1: Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "❌ Python not found. Install Python 3.9+ first."
    exit 1
fi
echo "   ✅ Found: $($PYTHON --version)"

# ── Step 2: Install dependencies ──
echo ""
echo "📋 Step 2: Installing dependencies..."
$PYTHON -m pip install -r requirements.txt -q
echo "   ✅ Dependencies installed"

# ── Step 3: Get OpenAI API Key ──
echo ""
echo "📋 Step 3: Connect your OpenAI account"
echo ""
echo "   Your OpenAI API key looks like: sk-proj-xxxxx..."
echo "   Get it from: https://platform.openai.com/api-keys"
echo ""

if [ -f .env ]; then
    echo "   Found existing .env file"
else
    cp .env.example .env
    echo "   Created .env from template"
fi

# Check if key is already set
EXISTING_KEY=$(grep "^OPENAI_API_KEY=" .env | cut -d'=' -f2)
if [ -n "$EXISTING_KEY" ] && [ "$EXISTING_KEY" != "sk-your-api-key-here" ] && [ -n "$EXISTING_KEY" ]; then
    echo "   ✅ Found existing API key: ${EXISTING_KEY:0:12}...${EXISTING_KEY: -4}"
    read -p "   Use this key? (Y/n): " USE_EXISTING
    if [ "$USE_EXISTING" = "n" ] || [ "$USE_EXISTING" = "N" ]; then
        EXISTING_KEY=""
    fi
fi

if [ -z "$EXISTING_KEY" ] || [ "$EXISTING_KEY" = "sk-your-api-key-here" ]; then
    read -p "   Paste your OpenAI API key: " API_KEY
    if [ -z "$API_KEY" ]; then
        echo "   ⚠️  No key entered. You can edit .env manually later."
    else
        # Update .env file
        if grep -q "^OPENAI_API_KEY=" .env; then
            sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$API_KEY|" .env
        else
            echo "OPENAI_API_KEY=$API_KEY" >> .env
        fi
        echo "   ✅ API key saved to .env"
    fi
fi

# ── Step 4: Choose broker ──
echo ""
echo "📋 Step 4: Choose broker"
echo "   1. Paper Trading (simulation, no real money) ← recommended first"
echo "   2. Alpaca (free paper account, then real trading)"
echo "   3. Interactive Brokers (professional)"
echo ""
read -p "   Choose [1/2/3] (default: 1): " BROKER_CHOICE

case $BROKER_CHOICE in
    2)
        echo ""
        echo "   🦙 Alpaca setup:"
        echo "   Sign up at: https://app.alpaca.markets/signup"
        read -p "   Alpaca API Key: " ALPACA_KEY
        read -p "   Alpaca Secret Key: " ALPACA_SECRET
        
        sed -i "s|^BROKER_TYPE=.*|BROKER_TYPE=alpaca|" .env
        sed -i "s|^ALPACA_API_KEY=.*|ALPACA_API_KEY=$ALPACA_KEY|" .env
        sed -i "s|^ALPACA_SECRET_KEY=.*|ALPACA_SECRET_KEY=$ALPACA_SECRET|" .env
        sed -i "s|^ALPACA_PAPER=.*|ALPACA_PAPER=true|" .env
        
        echo "   ✅ Alpaca configured (paper trading mode)"
        $PYTHON -m pip install alpaca-py -q 2>/dev/null || true
        ;;
    3)
        echo ""
        echo "   🏢 Interactive Brokers setup:"
        echo "   Make sure TWS or IB Gateway is running!"
        read -p "   Host (default: 127.0.0.1): " IBKR_HOST
        read -p "   Port (default: 7497): " IBKR_PORT
        
        IBKR_HOST=${IBKR_HOST:-127.0.0.1}
        IBKR_PORT=${IBKR_PORT:-7497}
        
        sed -i "s|^BROKER_TYPE=.*|BROKER_TYPE=ibkr|" .env
        sed -i "s|^IBKR_HOST=.*|IBKR_HOST=$IBKR_HOST|" .env
        sed -i "s|^IBKR_PORT=.*|IBKR_PORT=$IBKR_PORT|" .env
        
        echo "   ✅ IBKR configured"
        $PYTHON -m pip install ib_insync -q 2>/dev/null || true
        ;;
    *)
        sed -i "s|^BROKER_TYPE=.*|BROKER_TYPE=paper|" .env
        echo "   ✅ Paper trading configured"
        ;;
esac

# ── Done ──
echo ""
echo "🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞"
echo "✅ SETUP COMPLETE!"
echo "🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞🦞"
echo ""
echo "   To start trading:"
echo ""
echo "     $PYTHON main.py"
echo ""
echo "   Or auto-trading mode:"
echo ""
echo "     $PYTHON main.py --mode auto"
echo ""
echo "   Or pass API key directly:"
echo ""
echo "     $PYTHON main.py --api-key sk-proj-YOUR_KEY"
echo ""
echo "🦞 Happy Trading!"
