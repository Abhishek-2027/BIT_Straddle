"""Pydantic v2 domain models for the BTC ATM Short Straddle system."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StrategyState(str, Enum):
    """Lifecycle states of the straddle strategy."""

    IDLE = "IDLE"
    SELECTED = "SELECTED"
    QUOTING = "QUOTING"
    ARMED = "ARMED"
    ENTRY_SUBMITTED = "ENTRY_SUBMITTED"
    OPEN = "OPEN"
    UNBALANCED = "UNBALANCED"
    EXITING = "EXITING"
    CLOSED = "CLOSED"


# ---------------------------------------------------------------------------
# Core value objects
# ---------------------------------------------------------------------------

class OptionLeg(BaseModel):
    """A single option leg descriptor."""

    underlying: str
    kind: str  # "CALL" or "PUT"
    strike: Decimal
    expiry: datetime
    instrument_id: str
    tradable: bool


class SelectionResult(BaseModel):
    """Result of ATM straddle selection."""

    expiry: Optional[datetime] = None
    strike: Optional[Decimal] = None
    call_id: Optional[str] = None
    put_id: Optional[str] = None
    ref_price: Optional[Decimal] = None
    reason: Optional[str] = None


class RiskDecision(BaseModel):
    """Snapshot of the risk engine's evaluation."""

    entry_premium: Decimal
    buyback_cost: Decimal
    sl_threshold: Decimal
    tp_threshold: Decimal
    spread_pct: float
    decision: Optional[str] = None  # "STOP_LOSS", "TAKE_PROFIT", or None


class QuoteData(BaseModel):
    """Latest bid/ask quote for one instrument."""

    instrument_id: str
    bid: Decimal
    ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    timestamp: datetime


class PositionInfo(BaseModel):
    """Runtime position information."""

    instrument_id: str
    side: str
    qty: Decimal
    avg_entry: Decimal
    current_bid: Decimal = Decimal("0")
    current_ask: Decimal
    unrealized_pnl: Decimal


class OrderInfo(BaseModel):
    """An order's current state."""

    client_order_id: str
    instrument_id: str
    leg: str  # "CALL" or "PUT"
    side: str
    order_type: str
    qty: Decimal
    status: str
    filled_qty: Decimal
    avg_price: Optional[Decimal] = None
    timestamps: dict = {}


class StrategyEvent(BaseModel):
    """An event emitted by the strategy."""

    timestamp: datetime
    level: str
    code: str
    text: str


class StrategySnapshot(BaseModel):
    """Full snapshot of strategy state for the dashboard."""

    timestamp: datetime
    state: str
    mode: str
    selection: Optional[SelectionResult] = None
    quotes: dict = {}
    risk: Optional[RiskDecision] = None
    positions: list[PositionInfo] = []
    orders: list[OrderInfo] = []
    events: list[StrategyEvent] = []


# ---------------------------------------------------------------------------
# Commands / config updates
# ---------------------------------------------------------------------------

class ConfigUpdate(BaseModel):
    """Partial config update from the dashboard."""

    sl_pct: Optional[float] = None
    tp_pct: Optional[float] = None
    qty: Optional[float] = None
    max_spread_pct: Optional[float] = None


class CommandMessage(BaseModel):
    """A command sent from the dashboard to the strategy."""

    command: str  # "ARM", "DISARM", "FLATTEN", "UPDATE_CONFIG"
    payload: Optional[dict] = None
