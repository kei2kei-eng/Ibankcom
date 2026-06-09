# 🦞 AI Investment Bank — Hourly Report System (小龍蝦)

> **AI-powered hourly stock analysis with continuous learning**
> Scans the market every hour → Reviews last hour's picks → Learns → Reports to YOU → You decide.

## How It Works

Every **hour during market hours** (9:30 AM – 4:00 PM ET), the system runs this cycle:

```
┌─────────────────────────────────────────────────┐
│  📊 REVIEW: How did last hour's picks perform?  │
│  ↓                                               │
│  🌍 DISCOVER: Scan market for stocks             │
│  ↓                                               │
│  🔬 SCREEN: Rank top 50 by quantitative score    │
│  ↓                                               │
│  🔍 ANALYZE: Deep AI analysis on top 5           │
│  │         (6 agents + learning context)          │
│  ↓                                               │
│  📝 REPORT: Generate hourly HTML + text report   │
│  ↓                                               │
│  📚 LEARN: Adjust agent weights based on results │
│  ↓                                               │
│  📧 EMAIL: Send report to you                    │
└─────────────────────────────────────────────────┘
```

## Key Features

### 🔄 Hourly Cycle
- **9:35, 10:30, 11:30, 12:30, 13:30, 14:30, 15:30, 15:50** ET — 8 reports per trading day
- Each report is fresh — re-scans market data, re-ranks stocks, re-analyzes top picks

### 📊 "What Changed Since Last Hour"
- Every report shows a comparison table: **what we recommended last hour vs. what actually happened**
- Tracks per-stock accuracy: ✅ correct or ❌ incorrect
- Shows if target prices or stop losses were hit

### 📈 Multi-Hour Trend Tracking
- Tracks accuracy over the last 4 hours
- Trend indicator: IMPROVING / STABLE / DECLINING
- Generates learning insights from the trend

### 📚 Continuous Learning
- **HourlyTracker** saves every hour's decisions and compares with actual market moves
- **Adaptive Logic Engine** adjusts agent weights (agents that are right get more influence)
- **Decision Journal** records every decision in SQLite for long-term learning
- **Learning context** is injected into every agent's analysis prompt

### 🤖 7 AI Agents
| Agent | Role |
|-------|------|
| StockScreenerAgent | Quantitative scoring → Top 50 |
| MarketAnalystAgent | Technical analysis (RSI, MACD, SMA) |
| NewsAnalystAgent | News sentiment analysis |
| QuantAnalystAgent | Multi-factor quantitative model |
| RiskManagerAgent | Risk assessment |
| CEOAgent | Synthesizes all agents → final BUY/SELL/HOLD |
| ComplianceOfficerAgent | Approves/blocks risky trades |

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure your API key
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 3. Run one report now
```bash
python main.py --mode report
```

### 4. Run hourly during market hours
```bash
python main.py --mode hourly
```

### 5. Interactive mode
```bash
python main.py --mode interactive
```

## Run Modes

| Mode | Command | Description |
|------|---------|-------------|
| **report** | `--mode report` | Generate one hourly report now |
| **hourly** | `--mode hourly` | Run every hour during market hours |
| **interactive** | `--mode interactive` | Manual commands |

## Interactive Commands

| Command | Description |
|---------|-------------|
| `report` | Run full hourly pipeline |
| `review` | Show previous hour's performance |
| `discover` | Scan the market |
| `screen` | Screen → Top 50 |
| `top50` | Show Top 50 ranking |
| `analyze X` | Deep analyze one stock |
| `learn` | Run learning cycle |
| `status` | Show tracker status |
| `portfolio` | Show portfolio |

## Output Files

```
report_latest.html          ← Always the most recent hourly report
report_latest.txt           ← Plain text version
reports/
  report_20260608_0935.html  ← Archived reports with timestamps
  report_20260608_1030.html
  report_20260608_1130.html
  ...
hourly_tracker_state.json   ← Tracks decisions between hours
decision_journal.db         ← SQLite decision log for learning
```

## Telegram Setup (Recommended)

Get hourly reports sent directly to your phone!

### Step 1: Create a Telegram Bot
1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g., "My Stock AI")
4. Choose a username (e.g., `my_stock_ai_bot`)
5. **Copy the bot token** (looks like `123456:ABC-DEF1234ghIkl...`)

### Step 2: Get Your Chat ID
1. Send `/start` to your new bot
2. Search for **@userinfobot** and send it any message
3. **Copy your Chat ID** (a number like `123456789`)

### Step 3: Configure
Add to `.env`:
```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=123456789
```

### Step 4: Test
```bash
python telegram_sender.py
```

You'll receive a test message on Telegram. Then every hourly report will be sent as:
- 📱 **Summary message** with BUY/SELL/HOLD decisions
- 📊 **Individual stock analysis** messages
- 📈 **"What Changed"** comparison vs last hour
- 📄 **Full HTML report** as a downloadable file

## Email Delivery (Fallback)

If you prefer email, add to `.env`:
```
REPORT_EMAIL=your-email@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
SMTP_FROM=your-email@gmail.com
```

## Configuration

Key settings in `.env`:
- `OPENAI_API_KEY` — Required for AI analysis (without it, defaults to HOLD)
- `REPORT_TIME` — Not used in hourly mode (reports run hourly automatically)
- `OPENAI_MODEL` — Default: `gpt-4o`

## Learning System

The system gets smarter every hour:

1. **Decision Recording** — Every stock analysis is saved with full context
2. **Outcome Tracking** — Previous decisions are compared with actual price movements
3. **Agent Weight Adjustment** — Agents that make correct calls get more influence
4. **Parameter Tuning** — Each agent's internal parameters are adjusted
5. **Context Injection** — Learning feedback is injected into future agent prompts

## Disclaimer

⚠️ This is AI-generated analysis for YOUR reference only. This is NOT financial advice. Always do your own research before trading. AI models can be wrong. Past performance does not guarantee future results.
