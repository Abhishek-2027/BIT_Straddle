# BTC ATM Short Straddle

A Bybit options strategy built with NautilusTrader, a FastAPI control/status bridge, and a React dashboard. It implements the internship assignment's BTC ATM call/put short straddle and Level 2 buyback risk rules. No database is required; order and event history is held in memory for the current process only.

## What it does

- Connects NautilusTrader to Bybit and subscribes to BTC option data.
- Selects a matching call and put at the nearest available ATM strike/expiry.
- Submits sell orders for both legs and tracks acknowledgements, fills, positions, and strategy events.
- Values closing risk using both option ask quotes and the position quantities.
- Automatically buys back the legs at a 1% increase (stop-loss) or 2% decrease (take-profit) in combined buyback premium.
- Handles incomplete leg fills and avoids duplicate exit submissions.
- Provides strategy controls, live status, positions, BTC reference price, PnL/risk chart, and current-run order/event history.

Bybit does not provide atomic two-leg execution. The strategy tracks each leg separately and applies the configured orphan-leg handling if only one leg fills.

## Requirements

- Python 3.11+
- Node.js 18+ and npm
- A Bybit API key configured for the chosen environment, with the permissions needed to read market/account data and trade options

The default environment is **Demo Trading**. Use Demo first. Changing `BYBIT_ENVIRONMENT` to `MAINNET` can place real orders; verify the environment and API credentials before arming.

## Setup

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `BYBIT_TESTNET_API_KEY` and `BYBIT_TESTNET_API_SECRET` in `backend/.env` to the credentials for the selected Bybit environment. Do not share or commit API credentials.

### Frontend

```powershell
cd ..\frontend
npm install
```

## Run

In one terminal:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python main.py
```

In another terminal:

```powershell
cd frontend
npm run dev
```

Open the Vite URL printed in the frontend terminal (normally `http://localhost:5173`). The backend serves the REST API on port 8000 and the WebSocket feed at `/ws`.

## Operating flow

1. The backend starts the NautilusTrader node and reports its readiness in the dashboard.
2. The strategy discovers BTC option instruments, selects a same-expiry call and put around the BTC reference price, and subscribes to their quotes.
3. Arm the strategy only after the dashboard reports the node ready and both quotes are fresh. The strategy submits sell orders for both legs.
4. The dashboard receives state, order, fill, quote, position, and risk updates. An order being submitted is not the same as an exchange-confirmed fill.
5. To close manually, use **Flatten**. The Level 2 risk monitor also submits buyback orders when either threshold is reached.

No stop-loss, take-profit, or automated exit can guarantee a fill or a maximum loss. Exchange availability, liquidity, partial fills, and option price changes can affect execution. The application does not persist event/order history across backend restarts.

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `BYBIT_ENVIRONMENT` | `DEMO` | `DEMO`, `TESTNET`, or `MAINNET` |
| `BYBIT_TESTNET_API_KEY` | empty | API key for the configured environment |
| `BYBIT_TESTNET_API_SECRET` | empty | API secret for the configured environment |
| `SL_PCT` | `0.01` | Stop-loss increase in combined buyback premium |
| `TP_PCT` | `0.02` | Take-profit decrease in combined buyback premium |
| `QTY` | `0.01` | Requested quantity per option leg |
| `MAX_SPREAD_PCT` | `0.015` | Maximum spread gate for entry quotes |
| `STALE_QUOTE_SECS` | `5` | Maximum age for an executable quote |
| `EXIT_WATCHDOG_SECS` | `10` | Exit-order watchdog timeout |
| `AUTO_ENTER` | `false` | Automatically arm when the strategy is quoting |
| `ENTRY_ORDER_STYLE` | `ioc_limit` | Entry order style |
| `EXIT_ORDER_STYLE` | `ioc_limit` | Exit order style |
| `LEG_FAIL_POLICY` | `unwind` | Response to an unbalanced leg fill |
| `API_PORT` | `8000` | FastAPI port |

`BYBIT_TESTNET` is retained as a legacy compatibility setting; `BYBIT_ENVIRONMENT` is the authoritative environment selector.
