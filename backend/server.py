"""FastAPI server providing REST API and WebSocket streams for BTC Straddle."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

try:
    from backend.bridge import bridge
    from backend.config import settings
    from backend.models import ConfigUpdate, StrategyState
except ImportError:
    from bridge import bridge
    from config import settings
    from models import ConfigUpdate, StrategyState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WebSocket Manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Manages active WebSocket connections and broadcasting."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active_connections.append(ws)
        logger.info("WebSocket connected. Active clients: %d", len(self.active_connections))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active_connections:
            self.active_connections.remove(ws)
            logger.info("WebSocket disconnected. Active clients: %d", len(self.active_connections))

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Broadcast data to all connected clients, dropping dead ones."""
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception as e:
                logger.warning("Failed to send to client (%s), disconnecting", e)
                self.disconnect(connection)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Background Task: Bridge Dispatcher (Queue -> WebSocket)
# ---------------------------------------------------------------------------

async def bridge_dispatcher() -> None:
    """Continuously forward strategy events and snapshots to WebSocket clients."""
    logger.info("Bridge dispatcher background worker started")
    while True:
        try:
            # Drain batch of events from bridge without blocking the async event loop
            events = await asyncio.to_thread(bridge.get_events, 0.1)
            for event in events:
                if event.get("code") == "STRATEGY_READY":
                    _set_trading_status("ready")

                await manager.broadcast(event)

        except asyncio.CancelledError:
            logger.info("Bridge dispatcher task cancelled")
            break
        except Exception as e:
            logger.error("Bridge dispatcher error: %s", e)
            await asyncio.sleep(0.5)


# ---------------------------------------------------------------------------
# Lifespan: startup & shutdown
# ---------------------------------------------------------------------------

_trading_node = None
_trading_thread: Optional[threading.Thread] = None
_trading_status_lock = threading.Lock()
_trading_status: dict[str, Optional[str]] = {
    "state": "not_started",
    "message": None,
}


def _set_trading_status(state: str, message: Optional[str] = None) -> None:
    with _trading_status_lock:
        _trading_status["state"] = state
        _trading_status["message"] = message


def _get_trading_status() -> dict[str, Optional[str]]:
    with _trading_status_lock:
        return dict(_trading_status)


def _current_snapshot() -> dict[str, Any]:
    """Return live bridge state or a startup placeholder, never a prior-run snapshot."""
    snapshot = bridge.latest_snapshot
    if snapshot is not None:
        return snapshot

    trading = _get_trading_status()
    node_state = trading["state"]
    state = (
        "STARTING"
        if node_state in ("not_started", "starting", "stopping")
        else "ERROR"
        if node_state in ("error", "unavailable", "stopped")
        else "IDLE"
    )
    return {
        "type": "snapshot",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "node_status": node_state,
        "node_message": trading["message"],
        "mode": settings.BYBIT_ENVIRONMENT.lower(),
        "selection": None,
        "quotes": {},
        "risk": None,
        "positions": [],
        "orders": [],
        "config": {
            "sl_pct": settings.SL_PCT,
            "tp_pct": settings.TP_PCT,
            "qty": settings.QTY,
            "max_spread_pct": settings.MAX_SPREAD_PCT,
        },
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _trading_node, _trading_thread

    # 1. Startup: launch background bridge consumer
    dispatcher_task = asyncio.create_task(bridge_dispatcher())
    
    # 2. Launch NautilusTrader in a dedicated engine thread (skip during pytest)
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        def _run_node():
            global _trading_node
            _set_trading_status("starting")
            try:
                try:
                    from backend.node_factory import build_trading_node
                except ImportError:
                    from node_factory import build_trading_node

                logger.info("Initializing NautilusTrader node on engine thread...")
                _trading_node = build_trading_node()
                if _trading_node is not None:
                    logger.info("Building trading node...")
                    _trading_node.build()
                    _set_trading_status("starting", "Waiting for strategy startup and exchange reconciliation.")
                    logger.info("Running trading node on Bybit %s...", settings.BYBIT_ENVIRONMENT.title())
                    _trading_node.run()
                    _set_trading_status("stopped", "NautilusTrader stopped.")
                else:
                    logger.warning("NautilusTrader node could not be constructed.")
                    _set_trading_status(
                        "unavailable",
                        "Trading node was not created. Check Bybit credentials and adapter configuration.",
                    )
            except Exception as e:
                logger.exception("Error in NautilusTrader engine thread")
                _set_trading_status(
                    "error",
                    f"NautilusTrader failed to start ({type(e).__name__}). Check backend logs.",
                )

        _trading_thread = threading.Thread(target=_run_node, daemon=True, name="nautilus-engine")
        _trading_thread.start()
    else:
        _set_trading_status("disabled", "Trading node startup is disabled in tests.")
        logger.info("Skipping trading node startup in test environment.")

    yield

    # Shutdown: cancel dispatcher task
    dispatcher_task.cancel()
    try:
        await dispatcher_task
    except asyncio.CancelledError:
        pass

    # Stop trading node if active
    if _trading_node is not None:
        try:
            _set_trading_status("stopping")
            logger.info("Stopping NautilusTrader node...")
            _trading_node.stop()
            _set_trading_status("stopped")
        except Exception as e:
            _set_trading_status("error", "NautilusTrader failed to stop. Check backend logs.")
            logger.debug("Trading node stop exception: %s", e)


# ---------------------------------------------------------------------------
# FastAPI App Definition
# ---------------------------------------------------------------------------

app = FastAPI(
    title="BTC ATM Short Straddle API",
    description="Backend API and WebSocket feed for NautilusTrader Bybit Straddle",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    """Report API health and NautilusTrader node readiness."""
    trading = _get_trading_status()
    return {
        "status": "ok",
        "trading_node": trading["state"],
        "trading_message": trading["message"],
    }


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    """Return current-process state; historical snapshots are not live state."""
    return _current_snapshot()


@app.post("/api/arm")
async def arm_strategy() -> dict[str, Any]:
    """Command strategy to ARM and enter ATM straddle."""
    trading = _get_trading_status()
    if trading["state"] != "ready":
        detail = trading["message"] or f"Trading engine is {trading['state']}."
        raise HTTPException(status_code=503, detail=detail)
    bridge.push_command({"command": "ARM"})
    return {"status": "ok", "command": "ARM"}


@app.post("/api/disarm")
async def disarm_strategy() -> dict[str, Any]:
    """Command strategy to DISARM back to QUOTING state."""
    bridge.push_command({"command": "DISARM"})
    return {"status": "ok", "command": "DISARM"}


@app.post("/api/flatten")
async def flatten_strategy() -> dict[str, Any]:
    """Command strategy to close all open positions immediately."""
    bridge.push_command({"command": "FLATTEN"})
    return {"status": "ok", "command": "FLATTEN"}


@app.post("/api/reset")
async def reset_strategy() -> dict[str, Any]:
    """Emergency reset: cancels pending orders, sweeps open positions on Bybit, and returns to QUOTING."""
    bridge.push_command({"command": "RESET"})
    # Safeguard: perform direct Bybit sweep if pybit credentials exist
    try:
        import uuid
        import pybit.unified_trading as bybit
        if settings.BYBIT_TESTNET_API_KEY and settings.BYBIT_TESTNET_API_SECRET:
            session = bybit.HTTP(
                testnet=False,
                api_key=settings.BYBIT_TESTNET_API_KEY,
                api_secret=settings.BYBIT_TESTNET_API_SECRET,
                demo=True,
            )
            res = session.get_positions(category="option", baseCoin="BTC")
            positions = res.get("result", {}).get("list", [])
            for p in positions:
                sz = p.get("size")
                sym = p.get("symbol")
                side = "Buy" if p.get("side") == "Sell" else "Sell"
                if sz and float(sz) > 0 and sym:
                    session.place_order(
                        category="option",
                        symbol=sym,
                        side=side,
                        orderType="Market",
                        qty=sz,
                        orderLinkId=f"rst-{uuid.uuid4().hex[:10]}",
                    )
    except Exception as e:
        logger.warning("Bybit sweep during reset warning: %s", e)

    return {"status": "ok", "command": "RESET"}


def _persist_env_config(payload: dict[str, Any]) -> None:
    """Persist updated risk/sizing knobs to backend/.env if it exists."""
    env_paths = [
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    mapping = {
        "sl_pct": "SL_PCT",
        "tp_pct": "TP_PCT",
        "qty": "QTY",
        "max_spread_pct": "MAX_SPREAD_PCT",
    }
    for p in env_paths:
        if p.exists():
            try:
                lines = p.read_text(encoding="utf-8").splitlines()
                updated_lines = []
                keys_seen = set()
                for line in lines:
                    matched = False
                    for k, env_key in mapping.items():
                        if line.startswith(f"{env_key}=") and k in payload:
                            updated_lines.append(f"{env_key}={payload[k]}")
                            keys_seen.add(env_key)
                            matched = True
                            break
                    if not matched:
                        updated_lines.append(line)
                for k, env_key in mapping.items():
                    if k in payload and env_key not in keys_seen:
                        updated_lines.append(f"{env_key}={payload[k]}")
                p.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
            except Exception as e:
                logger.warning("Could not persist config to %s: %s", p, e)


@app.post("/api/config")
async def update_config(update: ConfigUpdate) -> dict[str, Any]:
    """Update strategy risk and sizing configuration."""
    # Check if straddle is currently in active trade
    snapshot = bridge.latest_snapshot
    if snapshot:
        current_state = snapshot.get("state")
        if current_state in (
            StrategyState.OPEN.value,
            StrategyState.ENTRY_SUBMITTED.value,
            StrategyState.EXITING.value,
            StrategyState.UNBALANCED.value,
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot update config while strategy state is '{current_state}'",
            )

    payload = update.model_dump(exclude_unset=True)
    if update.sl_pct is not None:
        settings.SL_PCT = float(update.sl_pct)
    if update.tp_pct is not None:
        settings.TP_PCT = float(update.tp_pct)
    if update.qty is not None:
        settings.QTY = float(update.qty)
    if update.max_spread_pct is not None:
        settings.MAX_SPREAD_PCT = float(update.max_spread_pct)

    _persist_env_config(payload)
    bridge.push_command({"command": "UPDATE_CONFIG", "payload": payload})
    return {"status": "ok", "updated": payload}


@app.get("/api/events")
async def get_events(
    since: Optional[str] = Query(None, description="ISO timestamp to filter events"),
    limit: int = Query(100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """Return recent events from this running strategy process."""
    dt: Optional[datetime] = None
    if since:
        try:
            dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ISO timestamp format for 'since'")

    events = bridge.recent_events
    if since and dt:
        events = [
            event for event in events
            if datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")) >= dt
        ]
    return events[-limit:]


@app.get("/api/orders")
async def get_orders() -> list[dict[str, Any]]:
    """Return exchange orders tracked by the current strategy process."""
    snapshot = bridge.latest_snapshot
    return snapshot.get("orders", []) if snapshot else []


# ---------------------------------------------------------------------------
# Market & Account Summary Endpoints
# ---------------------------------------------------------------------------

_market_cache: dict[str, Any] = {"ts": 0.0, "data": None}


@app.get("/api/market/btc")
async def get_btc_market() -> dict[str, Any]:
    """Fetch live BTC/USDT price, 24h metrics and sparkline from Bybit."""
    import time
    now = time.monotonic()
    if _market_cache["data"] and (now - _market_cache["ts"] < 2.0):
        return _market_cache["data"]

    try:
        import httpx
        public_base_url = settings.bybit_public_rest_base_url
        environment_label = settings.BYBIT_ENVIRONMENT.title()
        async with httpx.AsyncClient(timeout=3.0) as client:
            ticker_resp, kline_resp = await asyncio.gather(
                client.get(f"{public_base_url}/v5/market/tickers?category=linear&symbol=BTCUSDT"),
                client.get(f"{public_base_url}/v5/market/kline?category=linear&symbol=BTCUSDT&interval=15&limit=24"),
                return_exceptions=True,
            )
            if isinstance(ticker_resp, Exception):
                raise HTTPException(status_code=502, detail=f"Unable to retrieve Bybit {environment_label} BTC price")
            ticker_resp.raise_for_status()
            ticker_json = ticker_resp.json()
            ticker_list = ticker_json.get("result", {}).get("list") or []
            if ticker_json.get("retCode") != 0 or not ticker_list:
                raise HTTPException(status_code=502, detail=f"Bybit {environment_label} returned no BTC market price")
            ticker = ticker_list[0]
            data = {
                "price": float(ticker.get("lastPrice") or 0),
                "change24h": round(float(ticker.get("price24hPcnt") or 0) * 100, 2),
                "high24h": float(ticker.get("highPrice24h") or 0),
                "low24h": float(ticker.get("lowPrice24h") or 0),
                "sparkline": [],
                "environment": settings.BYBIT_ENVIRONMENT.lower(),
            }

            if not isinstance(kline_resp, Exception) and kline_resp.status_code == 200:
                k_json = kline_resp.json()
                if k_json.get("retCode") == 0 and k_json.get("result", {}).get("list"):
                    klines = k_json["result"]["list"]
                    sparkline = [float(k[4]) for k in reversed(klines)]
                    data["sparkline"] = sparkline

            if data["price"] <= 0:
                raise HTTPException(status_code=502, detail=f"Bybit {environment_label} returned an invalid BTC price")
            _market_cache["data"] = data
            _market_cache["ts"] = now
            return data
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Bybit market data request failed: %s", e)
        raise HTTPException(status_code=502, detail="Unable to retrieve Bybit market data") from e


# ---------------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_feed(websocket: WebSocket) -> None:
    """WebSocket endpoint streaming live strategy snapshots and events."""
    await manager.connect(websocket)

    # Immediately push the latest snapshot to the newly connected client
    snapshot_response = _current_snapshot()
    try:
        await websocket.send_json(snapshot_response)
        # Replay recent strategy events so Event Timeline is immediately populated on connect
        for ev in bridge.recent_events[-50:]:
            await websocket.send_json(ev)
    except Exception:
        pass

    try:
        while True:
            # Keep connection open; clients may send heartbeats or command messages
            data = await websocket.receive_text()
            # If client sends JSON commands via WS, handle them
            try:
                import json
                msg = json.loads(data)
                cmd = msg.get("command")
                if cmd:
                    bridge.push_command(msg)
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Static frontend files (if built)
# ---------------------------------------------------------------------------

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
