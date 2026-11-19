"""
NautilusTrader Strategy: BTC ATM Short Straddle.

State machine:
  IDLE → SELECTED → QUOTING → ARMED → ENTRY_SUBMITTED → OPEN
      → UNBALANCED → EXITING → CLOSED

Targeted at nautilus_trader >= 1.207.  Import paths may shift between
minor releases; comments note alternatives.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

# ── NautilusTrader core imports with version compatibility & mock fallbacks ──
try:
    from nautilus_trader.trading.strategy import Strategy
    from nautilus_trader.config import StrategyConfig
    from nautilus_trader.model.identifiers import InstrumentId, Venue, ClientOrderId
    from nautilus_trader.model.enums import OrderSide, TimeInForce, order_side_to_str
    from nautilus_trader.model.objects import Price, Quantity
    from nautilus_trader.model.events import (
        OrderFilled,
        OrderRejected,
        OrderAccepted,
        OrderCanceled,
        OrderSubmitted,
        OrderDenied,
    )
    from nautilus_trader.model.data import QuoteTick
    # Position may live in different spots depending on version
    try:
        from nautilus_trader.model.position import Position
    except ImportError:
        from nautilus_trader.model.objects import Position  # type: ignore[attr-defined]
    NAUTILUS_AVAILABLE = True
except ImportError:
    # Lightweight shims to support standalone environments, testing & simulation
    NAUTILUS_AVAILABLE = False
    from pydantic import BaseModel

    class StrategyConfig(BaseModel):
        pass

    class InstrumentId:
        def __init__(self, value: str):
            self.value = value
        @classmethod
        def from_str(cls, val: str):
            return cls(val)
        def __str__(self):
            return self.value
        def __repr__(self):
            return f"InstrumentId('{self.value}')"
        def __eq__(self, other):
            return str(self) == str(other)
        def __hash__(self):
            return hash(str(self))

    class Venue:
        def __init__(self, value: str):
            self.value = value
        def __str__(self):
            return self.value

    class ClientOrderId:
        def __init__(self, value: str):
            self.value = value
        def __str__(self):
            return self.value
        def __repr__(self):
            return f"ClientOrderId('{self.value}')"
        def __eq__(self, other):
            return str(self) == str(other)
        def __hash__(self):
            return hash(str(self))

    class OrderSide:
        BUY = "BUY"
        SELL = "SELL"

    def order_side_to_str(side):
        return str(side)

    class TimeInForce:
        IOC = "IOC"
        GTC = "GTC"
        FOK = "FOK"

    class Price:
        def __init__(self, val: Any):
            self.val = Decimal(str(val))
        @classmethod
        def from_str(cls, s: str):
            return cls(s)
        def __str__(self):
            return str(self.val)
        def __float__(self):
            return float(self.val)

    class Quantity:
        def __init__(self, val: Any):
            self.val = Decimal(str(val))
        @classmethod
        def from_str(cls, s: str):
            return cls(s)
        def __str__(self):
            return str(self.val)
        def __float__(self):
            return float(self.val)

    class QuoteTick:
        def __init__(self, instrument_id: Any, bid_price: Any, ask_price: Any, bid_size: Any, ask_size: Any, ts_event: int = 0):
            self.instrument_id = instrument_id
            self.bid_price = bid_price
            self.ask_price = ask_price
            self.bid_size = bid_size
            self.ask_size = ask_size
            self.ts_event = ts_event

    class Position:
        def __init__(self, instrument_id: Any, quantity: Any, avg_px_open: Any = Decimal(0), side: str = "SELL"):
            self.instrument_id = instrument_id
            self.quantity = Decimal(str(quantity))
            self.avg_px_open = Decimal(str(avg_px_open))
            self.side = side

    class _OrderMock:
        def __init__(self, client_order_id, instrument_id, order_side, quantity, price=None, time_in_force=None, reduce_only=False):
            self.client_order_id = client_order_id
            self.instrument_id = instrument_id
            self.order_side = order_side
            self.quantity = quantity
            self.price = price
            self.time_in_force = time_in_force
            self.reduce_only = reduce_only

    class _OrderFactoryMock:
        def __init__(self):
            self._counter = 0
        def limit(self, instrument_id, order_side, quantity, price, time_in_force=TimeInForce.IOC, reduce_only=False):
            self._counter += 1
            cid = ClientOrderId(f"MOCK-{self._counter}")
            return _OrderMock(cid, instrument_id, order_side, quantity, price, time_in_force, reduce_only)
        def market(self, instrument_id, order_side, quantity, time_in_force=TimeInForce.IOC, reduce_only=False):
            self._counter += 1
            cid = ClientOrderId(f"MOCK-{self._counter}")
            return _OrderMock(cid, instrument_id, order_side, quantity, None, time_in_force, reduce_only)

    class _CacheMock:
        def __init__(self):
            self._positions = {}
            self._instruments = []
        def instruments(self, venue=None):
            return self._instruments
        def position(self, instrument_id):
            return self._positions.get(str(instrument_id))

    class _ClockMock:
        def set_timer(self, name, interval, callback):
            pass

    class OrderEvent:
        def __init__(self, client_order_id, instrument_id=None, last_qty=0, last_px=0, reason=""):
            self.client_order_id = client_order_id
            self.instrument_id = instrument_id
            self.last_qty = last_qty
            self.last_px = last_px
            self.reason = reason

    class OrderFilled(OrderEvent): pass
    class OrderRejected(OrderEvent): pass
    class OrderAccepted(OrderEvent): pass
    class OrderCanceled(OrderEvent): pass
    class OrderSubmitted(OrderEvent): pass
    class OrderDenied(OrderEvent): pass

    class Strategy:
        def __init__(self, config):
            self.config = config
            self.cache = _CacheMock()
            self.clock = _ClockMock()
            self.order_factory = _OrderFactoryMock()
            self.submitted_orders = []
        def subscribe_quote_ticks(self, instrument_id): pass
        def submit_order(self, order):
            self.submitted_orders.append(order)

if "_OrderFactoryMock" not in globals():
    class _OrderFactoryMock:
        pass

# ── Internal imports ───────────────────────────────────────────────────
try:
    from backend.bridge import bridge
    from backend.models import StrategyState, OptionLeg
    from backend import selector, risk
    from backend.config import settings
except ImportError:
    from bridge import bridge
    from models import StrategyState, OptionLeg
    import selector, risk
    try:
        from config import settings
    except ImportError:
        settings = None

logger = logging.getLogger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────
_VENUE = Venue("BYBIT")
_SNAPSHOT_INTERVAL_S = 0.15  # max ~6-7 snapshots/sec
_EXIT_MAX_RETRIES = 5
_ASK_BUFFER_PCT = Decimal("0.005")  # 0.5 % above ask for exit limit price


def _quantize_price(
    price: Decimal | float,
    tick_size: Decimal | float = 5.0,
    rounding=ROUND_HALF_UP,
    precision: int | None = None,
) -> Price:
    tick = Decimal(str(tick_size)) if tick_size else Decimal("5")
    if tick <= 0:
        tick = Decimal("5")
    units = (Decimal(str(price)) / tick).to_integral_value(rounding=rounding)
    rounded = max(units * tick, tick)
    if precision is not None:
        return Price(float(rounded), precision)
    if rounded == rounded.to_integral():
        return Price.from_str(str(int(rounded)))
    return Price.from_str(format(rounded.normalize(), "f"))


# ═══════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════
class StraddleConfig(StrategyConfig):
    sl_pct: float = 0.01
    tp_pct: float = 0.02
    qty: float = 0.01
    max_spread_pct: float = 0.015
    stale_quote_secs: int = 5
    exit_watchdog_secs: int = 10
    auto_enter: bool = False
    entry_order_style: str = "ioc_limit"   # "ioc_limit" | "market"
    exit_order_style: str = "ioc_limit"
    leg_fail_policy: str = "unwind"        # "unwind" | "hold"


# ═══════════════════════════════════════════════════════════════════════
# Strategy
# ═══════════════════════════════════════════════════════════════════════
class StraddleStrategy(Strategy):
    """Short ATM straddle on BTC options via Bybit, managed by NautilusTrader."""

    def __init__(self, config: StraddleConfig) -> None:
        super().__init__(config)
        self.cfg = config

        # ── state ──────────────────────────────────────────────────────
        self._state: StrategyState = StrategyState.IDLE
        self._selection = None           # SelectionResult | None
        self._selection_candidates: list = []
        self._last_alternative_probe_ts: float = 0.0
        self._last_entry_wait_reason: str | None = None
        self._last_entry_wait_ts: float = 0.0
        self._call_id: InstrumentId | None = None
        self._put_id: InstrumentId | None = None

        # latest quotes keyed by instrument_id str
        self._quotes: dict[str, dict[str, Any]] = {}

        # entry tracking
        self._entry_premium: Decimal = Decimal(0)
        self._entry_orders: dict[str, ClientOrderId] = {}  # "CALL"/"PUT" → order id
        self._entry_order_legs: dict[str, str] = {}
        self._entry_fills: dict[str, dict] = {}             # "CALL"/"PUT" → fill info
        self._entry_targets: dict[str, Decimal] = {}
        self._entry_terminal_legs: set[str] = set()
        self._entry_cancel_requested_at: dict[str, float] = {}
        self._leg_multipliers: dict[str, Decimal] = {}
        self._order_status: dict[str, str] = {}
        self._order_submitted_at: dict[str, str] = {}
        self._order_submitted_monotonic: dict[str, float] = {}
        self._order_fills: dict[str, dict[str, Decimal]] = {}
        self._order_target_qty: dict[str, Decimal] = {}
        self._order_sides: dict[str, str] = {}

        # exit tracking
        self._exit_reason: str = ""
        self._exit_orders: dict[str, ClientOrderId] = {}
        self._exit_order_legs: dict[str, str] = {}
        self._active_exit_orders: dict[str, ClientOrderId] = {}
        self._exit_cancel_requested: set[str] = set()
        self._exit_cancel_requested_at: dict[str, float] = {}
        self._exit_targets: dict[str, Decimal] = {}
        self._last_exit_wait_reason: str | None = None
        self._last_exit_wait_ts: float = 0.0
        self._exit_fills: dict[str, dict] = {}
        self._exit_retries: dict[str, int] = {}
        self._entry_exit_orders_started = False
        self.submitted_orders: list = []
        self._mock_positions: dict[str, Any] = {}

        # snapshot throttle
        self._last_snapshot_ts: float = 0.0

        # events buffer for the bridge (relayed to DB via server thread)
        self._event_seq: int = 0
        self._last_instrument_discovery_ts: float = 0.0

        # Dynamic configuration overrides (mutable)
        self._sl_pct: float = float(config.sl_pct)
        self._tp_pct: float = float(config.tp_pct)
        self._qty: float = float(config.qty)
        self._max_spread_pct: float = float(config.max_spread_pct)

    @property
    def sl_pct(self) -> float:
        return self._sl_pct

    @property
    def tp_pct(self) -> float:
        return self._tp_pct

    @property
    def qty(self) -> float:
        return self._qty

    @property
    def max_spread_pct(self) -> float:
        return self._max_spread_pct

    @staticmethod
    def _accumulate_fill(
        fills: dict[str, dict],
        leg: str,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """Aggregate incremental executions into total quantity and weighted average price."""
        previous = fills.get(leg)
        if previous is None:
            fills[leg] = {"qty": quantity, "price": price}
            return

        total_qty = previous["qty"] + quantity
        if total_qty <= 0:
            return
        total_value = previous["qty"] * previous["price"] + quantity * price
        fills[leg] = {"qty": total_qty, "price": total_value / total_qty}

    def _record_order_fill(
        self,
        order_id: ClientOrderId,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        key = str(order_id)
        fill = self._order_fills.setdefault(
            key,
            {"qty": Decimal(0), "value": Decimal(0), "avg_price": Decimal(0)},
        )
        fill["qty"] += quantity
        fill["value"] += quantity * price
        fill["avg_price"] = fill["value"] / fill["qty"]

    # ── property helpers ───────────────────────────────────────────────
    @property
    def state(self) -> StrategyState:
        return self._state

    def _set_state(self, new: StrategyState) -> None:
        old = self._state
        self._state = new
        self._emit_event("STATE_CHANGE", f"{old.value} → {new.value}")
        logger.info("State: %s → %s", old.value, new.value)
        self._publish_snapshot()

    def _publish_snapshot(self) -> None:
        try:
            bridge.push_snapshot(self._build_snapshot())
        except Exception as e:
            logger.error("Snapshot publish failed: %s", e)

    def _instrument_multiplier(self, instrument_id: InstrumentId | None) -> Decimal:
        if instrument_id is None:
            return Decimal(1)
        cached = self._leg_multipliers.get(str(instrument_id))
        if cached is not None:
            return cached
        try:
            instrument = self.cache.instrument(instrument_id)
            multiplier = Decimal(str(instrument.multiplier))
            if multiplier > 0:
                self._leg_multipliers[str(instrument_id)] = multiplier
                return multiplier
        except Exception as e:
            logger.debug("Unable to read multiplier for %s: %s", instrument_id, e)
        return Decimal(1)

    def _remaining_exit_qty(self, leg: str) -> Decimal | None:
        target = self._exit_targets.get(leg)
        if target is None:
            target = self._entry_fills.get(leg, {}).get("qty")
        if target is None:
            return None
        exited = self._exit_fills.get(leg, {}).get("qty", Decimal(0))
        return max(Decimal(0), target - exited)

    # ── lifecycle ──────────────────────────────────────────────────────
    def _fetch_and_cache_bybit_instruments(self) -> list:
        """Fetch BTC options directly from Bybit REST and register into Nautilus cache."""
        self._last_instrument_discovery_ts = time.monotonic()
        try:
            import msgspec
            import httpx
            from nautilus_trader.adapters.bybit.schemas.instrument import BybitInstrumentOption
            from nautilus_trader.model.objects import Currency

            added = []
            usdt = Currency.from_str("USDT")
            cursor = None
            with httpx.Client(timeout=6.0) as client:
                for _ in range(20):
                    params = {"category": "option", "baseCoin": "BTC", "limit": 1000}
                    if cursor:
                        params["cursor"] = cursor
                    response = client.get(
                        f"{settings.bybit_public_rest_base_url}/v5/market/instruments-info",
                        params=params,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("retCode") != 0:
                        logger.warning(
                            "Bybit option instrument discovery failed (%s): %s",
                            payload.get("retCode"),
                            payload.get("retMsg", "unknown error"),
                        )
                        return added

                    result = payload.get("result", {})
                    for item in result.get("list", []):
                        if str(item.get("status", "")).upper() != "TRADING":
                            continue
                        try:
                            opt_obj = msgspec.json.decode(
                                msgspec.json.encode(item),
                                type=BybitInstrumentOption,
                            )
                            instrument = opt_obj.parse_to_instrument(usdt)
                            self.cache.add_instrument(instrument)
                            added.append(instrument)
                        except Exception as e:
                            logger.debug(
                                "Skipping unparseable Bybit option instrument %s: %s",
                                item.get("symbol", "unknown"),
                                e,
                            )
                    next_cursor = result.get("nextPageCursor")
                    if not next_cursor or next_cursor == cursor:
                        break
                    cursor = next_cursor
            logger.info("Direct REST fallback registered %d Bybit BTC options", len(added))
            return added
        except Exception as e:
            logger.warning("Direct REST fallback instrument discovery failed: %s", e)
            return []

    def on_start(self) -> None:
        logger.info("StraddleStrategy.on_start()")

        # Install command processing before the synchronous instrument/quote bootstrap.
        self.clock.set_timer(
            name="drain_commands",
            interval=timedelta(milliseconds=200),
            callback=self._on_drain_timer,
        )

        self.clock.set_timer(
            name="watchdog",
            interval=timedelta(seconds=max(self.cfg.exit_watchdog_secs, 5)),
            callback=self._on_watchdog,
        )

        self.clock.set_timer(
            name="poll_quotes",
            interval=timedelta(seconds=1),
            callback=self._on_poll_quotes,
        )

        # Instrument and quote bootstrap can perform synchronous Bybit REST requests.
        instruments = self.cache.instruments(venue=_VENUE)
        if not instruments:
            instruments = self._fetch_and_cache_bybit_instruments()

        if not instruments:
            self._emit_event("WARN", "No instruments in cache yet – watchdog will retry")
        else:
            self._run_selector(instruments)

        # Restart safety: check positions after the option instruments are selected.
        self._check_existing_positions()
        self._emit_event(
            "STRATEGY_READY",
            "Strategy initialized; waiting for live option quotes before submitting orders",
        )

    def on_stop(self) -> None:
        logger.info("StraddleStrategy.on_stop()")

    def on_dispose(self) -> None:
        logger.info("StraddleStrategy.on_dispose()")

    # ── selector ───────────────────────────────────────────────────────
    def _is_selection_expired(self) -> bool:
        """Return True if the current selection has reached or passed expiration."""
        if self._selection is None or getattr(self._selection, "expiry", None) is None:
            return False
        exp = self._selection.expiry
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp < (datetime.now(timezone.utc) - timedelta(minutes=5))

    def _run_selector(self, instruments) -> None:
        """Build OptionLeg list, pick ATM strike, subscribe to quotes."""
        was_armed = self._state == StrategyState.ARMED
        legs: list[OptionLeg] = []
        ref_prices: dict[str, Decimal] = {}

        for inst in instruments:
            # 1. Detect Option Kind (Call vs Put)
            kind = None
            if hasattr(inst, "option_kind") and inst.option_kind is not None:
                opt_k = inst.option_kind
                k_name = getattr(opt_k, "name", str(opt_k)).upper()
                k_repr = repr(opt_k).upper()
                if "CALL" in k_name or "CALL" in k_repr or k_name == "C" or opt_k == 1:
                    kind = "CALL"
                elif "PUT" in k_name or "PUT" in k_repr or k_name == "P" or opt_k == 2:
                    kind = "PUT"

            # 2. Strike Price
            strike = None
            if hasattr(inst, "strike_price") and inst.strike_price is not None:
                try:
                    strike = Decimal(str(inst.strike_price))
                except Exception:
                    pass

            # 3. Expiration Datetime
            expiry = None
            if hasattr(inst, "expiration_utc") and inst.expiration_utc is not None:
                exp_val = inst.expiration_utc
                if hasattr(exp_val, "to_pydatetime"):
                    expiry = exp_val.to_pydatetime()
                elif isinstance(exp_val, datetime):
                    expiry = exp_val
                if expiry and expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
            elif hasattr(inst, "expiration_ns") and inst.expiration_ns:
                try:
                    expiry = datetime.fromtimestamp(inst.expiration_ns / 1_000_000_000, tz=timezone.utc)
                except Exception:
                    pass

            # Fallback to info dict if not populated on Cython object directly
            info = getattr(inst, "info", {}) or {}
            if not kind:
                k_raw = info.get("optionType") or info.get("option_type") or ""
                if k_raw:
                    kind = "CALL" if k_raw.upper() in ("CALL", "C") else "PUT"
            if not strike:
                s_raw = info.get("strike") or info.get("strikePrice") or "0"
                try:
                    strike = Decimal(str(s_raw))
                except Exception:
                    pass
            if not expiry:
                e_raw = info.get("expiry") or info.get("deliveryTime") or info.get("expiryDate")
                if isinstance(e_raw, (int, float)):
                    expiry = datetime.fromtimestamp(float(e_raw) / 1000 if float(e_raw) > 1e12 else float(e_raw), tz=timezone.utc)
                elif isinstance(e_raw, str):
                    try:
                        expiry = datetime.fromisoformat(e_raw.replace("Z", "+00:00"))
                    except Exception:
                        pass

            if not kind or not strike or not expiry:
                continue

            # Check BTC underlying
            und = str(getattr(inst, "underlying", "BTC")).upper()
            inst_str = str(getattr(inst, "id", "")).upper()
            if "BTC" not in und and "BTC" not in inst_str:
                continue
            status = str(info.get("status", "Trading")).upper()
            if status != "TRADING" or getattr(inst, "is_active", True) is False:
                continue

            legs.append(OptionLeg(
                underlying="BTC",
                kind=kind,
                strike=strike,
                expiry=expiry,
                instrument_id=str(getattr(inst, "id", inst_str)),
                tradable=True,
            ))

            # Ref price: use underlying price from info if available
            expiry_key = expiry.isoformat()
            if expiry_key not in ref_prices:
                ref_p = info.get("underlyingPrice") or info.get("indexPrice")
                if ref_p:
                    ref_prices[expiry_key] = Decimal(str(ref_p))

        if not legs:
            self._selection_candidates = []
            self._selection = selector.select_atm_straddle([], {}, datetime.now(timezone.utc))
            self._emit_event("SELECTION_FAIL", self._selection.reason or "No tradable BTC option instruments")
            self._publish_snapshot()
            return

        if not ref_prices or "default" not in ref_prices:
            # Query real-time Bybit linear ticker for BTC index price
            try:
                import httpx
                resp = httpx.get(
                    f"{settings.bybit_public_rest_base_url}/v5/market/tickers?category=linear&symbol=BTCUSDT",
                    timeout=3.0,
                ).json()
                if resp.get("retCode") == 0 and resp.get("result", {}).get("list"):
                    ticker = resp["result"]["list"][0]
                    p = ticker.get("indexPrice") or ticker.get("lastPrice")
                    if p:
                        ref_prices["default"] = Decimal(str(p))
            except Exception as e:
                logger.debug("Failed to fetch live BTC reference price: %s", e)

        now = datetime.now(timezone.utc)
        candidates = selector.rank_atm_straddles(legs, ref_prices, now)
        self._selection_candidates = candidates
        result = candidates[0] if candidates else selector.select_atm_straddle(legs, ref_prices, now)
        self._selection = result

        if result.reason:
            self._emit_event("SELECTION_FAIL", result.reason)
            try:
                bridge.push_snapshot(self._build_snapshot())
            except Exception:
                pass
            return

        self._call_id = InstrumentId.from_str(result.call_id)
        self._put_id = InstrumentId.from_str(result.put_id)
        self._selection_candidate_index = 0
        self._instrument_multiplier(self._call_id)
        self._instrument_multiplier(self._put_id)

        try:
            self.subscribe_quote_ticks(self._call_id)
            self.subscribe_quote_ticks(self._put_id)
        except Exception as e:
            logger.debug("subscribe_quote_ticks error: %s", e)

        self._set_state(StrategyState.ARMED if was_armed else StrategyState.QUOTING)
        self._emit_event("SELECTED", f"strike={result.strike} expiry={result.expiry} call={result.call_id} put={result.put_id}")

        # Fetch initial quotes immediately so Live Quotes table is populated instantly
        try:
            self._on_poll_quotes()
        except Exception:
            pass

        if self.cfg.auto_enter:
            self._set_state(StrategyState.ARMED)

        try:
            bridge.push_snapshot(self._build_snapshot())
        except Exception as e:
            logger.error("Snapshot error in _set_state: %s", e)

    # ── restart safety ─────────────────────────────────────────────────
    def _check_existing_positions(self) -> None:
        """If positions are already open (node restarted), resume in OPEN state."""
        if self._call_id is None or self._put_id is None:
            return
        call_pos = self._get_position(self._call_id)
        put_pos = self._get_position(self._put_id)
        if not call_pos and not put_pos:
            return

        self._entry_fills = {}
        self._exit_targets = {}
        all_short = True
        for leg, instrument_id, position in (
            ("CALL", self._call_id, call_pos),
            ("PUT", self._put_id, put_pos),
        ):
            if position is None:
                continue
            qty = abs(Decimal(str(position.quantity)))
            self._exit_targets[leg] = qty
            side = self._position_side(position)
            if side not in ("SHORT", "SELL"):
                all_short = False
                continue
            self._entry_fills[leg] = {
                "qty": qty,
                "price": Decimal(str(position.avg_px_open)),
            }
            self._instrument_multiplier(instrument_id)

        if call_pos and put_pos and all_short:
            self._entry_premium = risk.entry_premium([
                (
                    fill["qty"],
                    fill["price"],
                    self._instrument_multiplier(instrument_id),
                )
                for leg, instrument_id in (
                    ("CALL", self._call_id),
                    ("PUT", self._put_id),
                )
                if (fill := self._entry_fills.get(leg)) is not None
            ])
            self._set_state(StrategyState.OPEN)
            self._emit_event("RESTART", "Resumed with open positions on both legs")
        else:
            self._set_state(StrategyState.UNBALANCED)
            self._emit_event(
                "RESTART",
                "Existing selected-contract positions are unbalanced or not both short; review before trading",
            )

    @staticmethod
    def _position_side(position) -> str:
        side = getattr(position, "side", "")
        return str(getattr(side, "name", side)).upper()

    def _get_position(self, instrument_id: InstrumentId):
        """Safely get position from cache; returns None if flat / not found."""
        sid = str(instrument_id)
        if hasattr(self, "_mock_positions") and sid in self._mock_positions:
            return self._mock_positions[sid]

        cache = getattr(self, "cache", None)
        positions_open = getattr(cache, "positions_open", None)
        if callable(positions_open):
            try:
                positions = [
                    pos
                    for pos in positions_open(venue=_VENUE, instrument_id=instrument_id)
                    if abs(Decimal(str(pos.quantity))) > 0
                ]
                if len(positions) == 1:
                    return positions[0]
                if positions:
                    from types import SimpleNamespace

                    signed_qty = sum(
                        (
                            abs(Decimal(str(pos.quantity)))
                            if self._position_side(pos) == "LONG"
                            else -abs(Decimal(str(pos.quantity)))
                            for pos in positions
                        ),
                        Decimal(0),
                    )
                    if signed_qty == 0:
                        return None
                    net_side = "LONG" if signed_qty > 0 else "SHORT"
                    same_side = [
                        pos for pos in positions
                        if self._position_side(pos) == net_side
                    ]
                    quantity = abs(signed_qty)
                    avg_px_open = sum(
                        (
                            abs(Decimal(str(pos.quantity)))
                            * Decimal(str(pos.avg_px_open))
                            for pos in same_side
                        ),
                        Decimal(0),
                    ) / sum(
                        (abs(Decimal(str(pos.quantity))) for pos in same_side),
                        Decimal(0),
                    )
                    logger.warning(
                        "Aggregating multiple open %s positions for %s",
                        net_side,
                        instrument_id,
                    )
                    return SimpleNamespace(
                        instrument_id=instrument_id,
                        quantity=quantity,
                        avg_px_open=avg_px_open,
                        side=net_side,
                    )
            except Exception as e:
                logger.warning("Unable to query open position for %s: %s", instrument_id, e)

        try:
            if hasattr(cache, "_positions") and sid in cache._positions:
                return cache._positions[sid]
        except Exception as e:
            logger.debug("Position cache fallback failed for %s: %s", instrument_id, e)

        if self._state in (StrategyState.OPEN, StrategyState.EXITING):
            leg = "CALL" if str(instrument_id) == str(self._call_id) else ("PUT" if str(instrument_id) == str(self._put_id) else None)
            if leg and leg in self._entry_fills:
                exited_qty = self._exit_fills.get(leg, {}).get("qty", Decimal(0))
                remaining_qty = self._entry_fills[leg]["qty"] - exited_qty
                if remaining_qty <= 0:
                    return None
                from types import SimpleNamespace
                return SimpleNamespace(
                    instrument_id=instrument_id,
                    quantity=remaining_qty,
                    avg_px_open=self._entry_fills[leg]["price"],
                    side="SELL"
                )
        return None

    # ── quotes ─────────────────────────────────────────────────────────
    def _on_poll_quotes(self, event=None) -> None:
        """Ensure both selected legs have fresh live quotes.
        Mark-derived prices are indicative only and are never executable.
        """
        if self._call_id is None or self._put_id is None:
            return

        now = time.time()
        call_key = str(self._call_id)
        put_key = str(self._put_id)
        cq = self._quotes.get(call_key)
        pq = self._quotes.get(put_key)

        need_call = cq is None or (now - cq["timestamp"]) > 1.5
        need_put = pq is None or (now - pq["timestamp"]) > 1.5

        if not need_call and not need_put:
            if self._state == StrategyState.ARMED:
                self._evaluate_armed_entry()
            return

        try:
            import httpx
            c_sym = self._call_id.symbol.value.replace("-OPTION", "")
            p_sym = self._put_id.symbol.value.replace("-OPTION", "")

            updated = False
            for sym, inst_id, need in [(c_sym, call_key, need_call), (p_sym, put_key, need_put)]:
                if not need:
                    continue
                resp = httpx.get(
                    f"{settings.bybit_public_rest_base_url}/v5/market/tickers?category=option&symbol={sym}",
                    timeout=2.0,
                ).json()
                if resp.get("retCode") == 0 and resp.get("result", {}).get("list"):
                    t = resp["result"]["list"][0]
                    bid = Decimal(str(t.get("bid1Price") or 0))
                    ask = Decimal(str(t.get("ask1Price") or 0))
                    bid_sz = Decimal(str(t.get("bid1Size") or 0))
                    ask_sz = Decimal(str(t.get("ask1Size") or 0))
                    mark = Decimal(str(t.get("markPrice") or 0))
                    is_synthetic = False

                    if (bid <= 0 or (mark > 0 and bid < mark * Decimal("0.5"))) and mark > 0:
                        bid = Decimal(str(round(float(mark) * 0.995, 2)))
                        is_synthetic = True
                    if (ask <= 0 or (mark > 0 and ask > mark * Decimal("1.5"))) and mark > 0:
                        ask = Decimal(str(round(float(mark) * 1.005, 2)))
                        is_synthetic = True

                    if bid > 0 and ask > 0:
                        existing_quote = self._quotes.get(inst_id)
                        if is_synthetic and existing_quote and not existing_quote.get("is_synthetic"):
                            continue
                        self._quotes[inst_id] = {
                            "instrument_id": inst_id,
                            "bid": bid,
                            "ask": ask,
                            "bid_size": bid_sz,
                            "ask_size": ask_sz,
                            "timestamp": time.time(),
                            "is_synthetic": is_synthetic,
                        }
                        updated = True

            if updated:
                if self._state == StrategyState.OPEN:
                    self._check_risk()
                elif self._state == StrategyState.EXITING:
                    self._retry_exit_leg("CALL")
                    self._retry_exit_leg("PUT")
                bridge.push_snapshot(self._build_snapshot())

            if self._state == StrategyState.ARMED:
                self._evaluate_armed_entry()
        except Exception as e:
            logger.debug("Quote poll notice: %s", e)
            if self._state == StrategyState.ARMED:
                self._emit_entry_wait(f"Quote refresh failed: {e}")

    def _entry_quote_block_reason(self) -> str | None:
        """Explain why the selected pair cannot safely submit sell orders yet."""
        if self._call_id is None or self._put_id is None:
            return "ATM call/put selection is not ready"
        if self._is_selection_expired():
            return "Selected options have expired; awaiting new expiry selection"

        quantity = Decimal(str(self.qty))
        quotes = []
        for leg, instrument_id in (("CALL", self._call_id), ("PUT", self._put_id)):
            quote = self._quotes.get(str(instrument_id))
            if quote is None:
                return f"Waiting for {leg} live bid/ask quotes"
            if time.time() - quote["timestamp"] > self.cfg.stale_quote_secs:
                return f"{leg} quote is stale; waiting for a fresh market update"
            if quote.get("is_synthetic"):
                return f"{leg} has only an indicative mark; waiting for a real order book"
            if quote["bid"] <= 0 or quote["ask"] <= 0 or quote["bid"] > quote["ask"]:
                return f"{leg} order book has no valid two-sided market"
            if quote["bid_size"] < quantity:
                return f"{leg} bid size is below sell quantity {quantity}"
            quotes.append(quote)

        spread = risk.spread_pct(
            [quote["bid"] for quote in quotes],
            [quote["ask"] for quote in quotes],
        )
        if spread > self.max_spread_pct:
            return (
                f"Combined spread {spread:.2%} exceeds limit "
                f"{self.max_spread_pct:.2%}"
            )
        return None

    def _has_executable_entry_quotes(self) -> bool:
        """Check that the selected pair has fresh, real, adequately sized BBOs."""
        return self._entry_quote_block_reason() is None

    def _emit_entry_wait(self, reason: str) -> None:
        now = time.monotonic()
        if reason != self._last_entry_wait_reason or now - self._last_entry_wait_ts >= 5.0:
            self._emit_event("ENTRY_WAIT", reason)
            self._last_entry_wait_reason = reason
            self._last_entry_wait_ts = now

    def _evaluate_armed_entry(self) -> None:
        if self._has_executable_entry_quotes():
            self._attempt_entry()
            return

        if self._select_executable_alternative():
            return

        reason = self._entry_quote_block_reason()
        if reason:
            if len(self._selection_candidates) > 1:
                reason += "; checking nearby strikes for liquidity"
            self._emit_entry_wait(reason)

    def _select_executable_alternative(self) -> bool:
        """Fall back to the nearest strike with real executable quotes, never mark prices."""
        if len(self._selection_candidates) < 2:
            return False

        now = time.monotonic()
        if now - self._last_alternative_probe_ts < 3.0:
            return False
        self._last_alternative_probe_ts = now

        try:
            import httpx

            response = httpx.get(
                f"{settings.bybit_public_rest_base_url}/v5/market/tickers?category=option&baseCoin=BTC",
                timeout=3.0,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("retCode") != 0:
                logger.warning(
                    "Bybit option ticker fallback failed (%s): %s",
                    payload.get("retCode"),
                    payload.get("retMsg", "unknown error"),
                )
                return False
            tickers = {
                str(ticker.get("symbol")): ticker
                for ticker in payload.get("result", {}).get("list", [])
                if ticker.get("symbol")
            }
        except Exception as e:
            logger.warning("Unable to check alternate BTC option order books: %s", e)
            return False

        current_ids = {str(self._call_id), str(self._put_id)}
        quantity = Decimal(str(self.qty))
        for index, candidate in enumerate(self._selection_candidates):
            if index == getattr(self, "_selection_candidate_index", 0):
                continue
            call_id = InstrumentId.from_str(candidate.call_id)
            put_id = InstrumentId.from_str(candidate.put_id)
            if {str(call_id), str(put_id)} == current_ids:
                continue

            leg_quotes = []
            for instrument_id in (call_id, put_id):
                symbol = instrument_id.symbol.value.replace("-OPTION", "")
                ticker = tickers.get(symbol)
                if ticker is None:
                    break
                bid = Decimal(str(ticker.get("bid1Price") or 0))
                ask = Decimal(str(ticker.get("ask1Price") or 0))
                bid_size = Decimal(str(ticker.get("bid1Size") or 0))
                ask_size = Decimal(str(ticker.get("ask1Size") or 0))
                if (
                    bid <= 0
                    or ask <= 0
                    or bid > ask
                    or bid_size < quantity
                ):
                    break
                leg_quotes.append({
                    "instrument_id": str(instrument_id),
                    "bid": bid,
                    "ask": ask,
                    "bid_size": bid_size,
                    "ask_size": ask_size,
                    "timestamp": time.time(),
                    "is_synthetic": False,
                })
            if len(leg_quotes) != 2:
                continue
            if risk.spread_pct(
                [quote["bid"] for quote in leg_quotes],
                [quote["ask"] for quote in leg_quotes],
            ) > self.max_spread_pct:
                continue

            previous_strike = self._selection.strike if self._selection else "unknown"
            self._call_id = call_id
            self._put_id = put_id
            self._selection = candidate
            self._selection_candidate_index = index
            self._quotes[str(call_id)] = leg_quotes[0]
            self._quotes[str(put_id)] = leg_quotes[1]
            try:
                self.subscribe_quote_ticks(call_id)
                self.subscribe_quote_ticks(put_id)
            except Exception:
                logger.exception("Failed to subscribe to alternate option quotes; REST quotes remain enabled")

            self._emit_event(
                "SELECTION_LIQUIDITY_FALLBACK",
                f"ATM strike {previous_strike} lacks executable BBOs; "
                f"selected nearest liquid strike {candidate.strike}",
            )
            bridge.push_snapshot(self._build_snapshot())
            self._attempt_entry()
            return True

        self._emit_event(
            "ENTRY_WAIT",
            "No paired strike in the nearest expiry currently has live quotes and sufficient size; waiting for order books",
        )
        return False

    def on_quote_tick(self, tick: QuoteTick) -> None:
        inst_id = str(tick.instrument_id)
        received_ns = getattr(tick, "ts_init", 0)
        received_at = received_ns / 1e9 if received_ns else time.time()
        self._quotes[inst_id] = {
            "instrument_id": inst_id,
            "bid": Decimal(str(tick.bid_price)),
            "ask": Decimal(str(tick.ask_price)),
            "bid_size": Decimal(str(tick.bid_size)),
            "ask_size": Decimal(str(tick.ask_size)),
            "timestamp": received_at,
            "is_synthetic": False,
        }

        # Risk check while OPEN or entry attempt while ARMED
        if self._state == StrategyState.OPEN:
            self._check_risk()
        elif self._state == StrategyState.ARMED:
            self._evaluate_armed_entry()
        elif self._state == StrategyState.EXITING:
            leg = "CALL" if inst_id == str(self._call_id) else "PUT" if inst_id == str(self._put_id) else None
            if leg:
                self._retry_exit_leg(leg)

        # Throttled snapshot
        now = time.monotonic()
        if now - self._last_snapshot_ts >= _SNAPSHOT_INTERVAL_S:
            self._last_snapshot_ts = now
            bridge.push_snapshot(self._build_snapshot())

    def _quotes_fresh(self) -> bool:
        """Return True if both legs have quotes younger than stale_quote_secs."""
        if self._call_id is None or self._put_id is None:
            return False
        now = time.time()
        for key in (str(self._call_id), str(self._put_id)):
            q = self._quotes.get(key)
            if q is None:
                return False
            if now - q["timestamp"] > self.cfg.stale_quote_secs:
                return False
        return True

    # ── risk ───────────────────────────────────────────────────────────
    def _check_risk(self) -> None:
        if self._call_id is None or self._put_id is None:
            return
        cq = self._quotes.get(str(self._call_id))
        pq = self._quotes.get(str(self._put_id))
        if cq is None or pq is None:
            return
        if not self._quotes_fresh() or cq.get("is_synthetic") or pq.get("is_synthetic"):
            return
        if cq["ask"] <= 0 or pq["ask"] <= 0:
            return

        asks = [cq["ask"], pq["ask"]]
        call_qty = self._entry_fills.get("CALL", {}).get("qty", Decimal(str(self.qty)))
        put_qty = self._entry_fills.get("PUT", {}).get("qty", Decimal(str(self.qty)))
        cost = risk.buyback_cost(
            [
                (call_qty, asks[0], self._instrument_multiplier(self._call_id)),
                (put_qty, asks[1], self._instrument_multiplier(self._put_id)),
            ],
            asks,
        )
        decision = risk.decide(cost, self._entry_premium, self.sl_pct, self.tp_pct)
        if decision is not None:
            self._request_exit(f"risk:{decision}")

    # ── entry ──────────────────────────────────────────────────────────
    def _attempt_entry(self) -> None:
        """Submit entry orders for both legs if conditions are met."""
        if self._state != StrategyState.ARMED:
            return
        if self._call_id is None or self._put_id is None:
            self._emit_event("ENTRY_SKIP", "Selection not ready")
            return

        if self._is_selection_expired():
            self._emit_event("ENTRY_WAIT", "Selected options have expired; awaiting new expiry selection")
            return

        # Check no existing positions
        if self._get_position(self._call_id) or self._get_position(self._put_id):
            self._emit_event("ENTRY_SKIP", "Existing positions detected")
            return

        if not self._quotes_fresh():
            self._emit_event("ENTRY_WAIT", "Waiting for fresh quotes")
            return

        cq = self._quotes[str(self._call_id)]
        pq = self._quotes[str(self._put_id)]
        for leg, quote in (("CALL", cq), ("PUT", pq)):
            if quote.get("is_synthetic"):
                self._emit_entry_wait(f"{leg} has only an indicative mark; waiting for a real order book")
                return
            if quote["bid_size"] < Decimal(str(self.qty)):
                self._emit_entry_wait(f"{leg} bid size is below sell quantity {self.qty}")
                return

        if cq["bid"] <= 0 or pq["bid"] <= 0:
            self._emit_event("ENTRY_SKIP", "Zero bid")
            return

        # Spread check
        bids = [cq["bid"], pq["bid"]]
        asks = [cq["ask"], pq["ask"]]
        spread = risk.spread_pct(bids, asks)
        if spread > self.max_spread_pct:
            self._emit_entry_wait(
                f"Combined spread {spread:.2%} exceeds limit {self.max_spread_pct:.2%}"
            )
            return

        qty = Quantity.from_str(str(self.qty))

        self._entry_fills = {}
        self._entry_orders = {}
        self._entry_targets = {}
        self._entry_terminal_legs = set()
        self._exit_fills = {}

        for leg_label, inst_id, bid in [("CALL", self._call_id, cq["bid"]), ("PUT", self._put_id, pq["bid"])]:
            coid = None
            if self.order_factory is not None:
                inst = self.cache.instrument(inst_id) if getattr(self, "cache", None) is not None else None
                order_qty = inst.make_qty(self.qty) if inst else qty
                self._entry_targets[leg_label] = Decimal(str(order_qty))
                tick_sz = inst.price_increment.as_double() if inst and hasattr(inst, "price_increment") else 5.0
                prec = inst.price_precision if inst and hasattr(inst, "price_precision") else None
                order_price = _quantize_price(bid, tick_sz, ROUND_FLOOR, precision=prec)
                if self.cfg.entry_order_style == "market":
                    order = self.order_factory.market(
                        instrument_id=inst_id,
                        order_side=OrderSide.SELL,
                        quantity=order_qty,
                        time_in_force=TimeInForce.IOC,
                    )
                else:
                    # IOC limit at bid
                    order = self.order_factory.limit(
                        instrument_id=inst_id,
                        order_side=OrderSide.SELL,
                        quantity=order_qty,
                        price=order_price,
                        time_in_force=TimeInForce.IOC,
                    )
                coid = order.client_order_id
                self.submitted_orders.append(order)
                self._entry_orders[leg_label] = coid
                self._entry_order_legs[str(coid)] = leg_label
                self._order_status[str(coid)] = "SUBMITTED"
                self._order_submitted_at[str(coid)] = datetime.now(timezone.utc).isoformat()
                self._order_submitted_monotonic[str(coid)] = time.monotonic()
                self._order_target_qty[str(coid)] = self._entry_targets[leg_label]
                self._order_sides[str(coid)] = "SELL"
                try:
                    self.submit_order(order)
                except Exception as e:
                    logger.exception("Failed to submit %s entry order", leg_label)
                    self._order_status[str(coid)] = "REJECTED"
                    self._emit_event("ORDER_SUBMIT_FAILED", f"{leg_label} entry submission failed: {e}")
                    self._entry_terminal_legs.add(leg_label)
            else:
                from types import SimpleNamespace
                coid = ClientOrderId(f"O-TEST-{leg_label}-{int(time.time()*1000)}")
                self._entry_targets[leg_label] = Decimal(str(self.qty))
                mock_order = SimpleNamespace(
                    client_order_id=coid,
                    instrument_id=inst_id,
                    order_side=OrderSide.SELL,
                    quantity=qty,
                    price=bid,
                    reduce_only=False,
                )
                self.submitted_orders.append(mock_order)
                self._entry_orders[leg_label] = coid
                self._entry_order_legs[str(coid)] = leg_label
                self._order_status[str(coid)] = "SUBMITTED"
                self._order_submitted_at[str(coid)] = datetime.now(timezone.utc).isoformat()
                self._order_submitted_monotonic[str(coid)] = time.monotonic()
                self._order_target_qty[str(coid)] = self._entry_targets[leg_label]
                self._order_sides[str(coid)] = "SELL"
            self._emit_event("ENTRY_SUBMIT", f"{leg_label} order {coid}")

        self._set_state(StrategyState.ENTRY_SUBMITTED)

        if self._entry_terminal_legs:
            for leg in tuple(self._entry_terminal_legs):
                self._handle_entry_leg_failure(leg)

    # ── exit ───────────────────────────────────────────────────────────
    def _request_exit(self, reason: str) -> None:
        """Begin orderly exit of both legs."""
        if self._state in (StrategyState.EXITING, StrategyState.CLOSED):
            return
        self._exit_reason = reason
        self._set_state(StrategyState.EXITING)
        self._emit_event("EXIT_START", reason)
        self._exit_retries = {"CALL": 0, "PUT": 0}
        self._exit_orders = {}
        self._active_exit_orders = {}
        self._exit_cancel_requested = set()
        self._exit_cancel_requested_at = {}
        self._exit_fills = {}
        self._exit_targets = {}
        for leg, instrument_id in (("CALL", self._call_id), ("PUT", self._put_id)):
            fill = self._entry_fills.get(leg)
            position = self._get_position(instrument_id) if instrument_id else None
            if fill:
                self._exit_targets[leg] = fill["qty"]
            elif position:
                self._exit_targets[leg] = abs(Decimal(str(position.quantity)))

        if self._pending_entry_legs():
            self._cancel_pending_entry_orders()
            return

        self._continue_exit_after_entry()

    def _pending_entry_legs(self) -> list[str]:
        """Return entry legs whose exchange orders may still fill."""
        return [
            leg
            for leg in ("CALL", "PUT")
            if leg in self._entry_orders
            and leg not in self._entry_terminal_legs
            and self._entry_fills.get(leg, {}).get("qty", Decimal(0))
            < self._entry_targets.get(leg, Decimal(str(self.qty)))
        ]

    def _cancel_pending_entry_orders(self) -> bool:
        """Request cancellation of any entry orders before closing their fills."""
        pending = self._pending_entry_legs()
        for leg in pending:
            order_id = self._entry_orders[leg]
            order_key = str(order_id)
            requested_at = self._entry_cancel_requested_at.get(order_key)
            if (
                requested_at is not None
                and time.monotonic() - requested_at < self.cfg.exit_watchdog_secs
            ):
                continue
            order = next(
                (item for item in self.submitted_orders
                 if str(getattr(item, "client_order_id", "")) == str(order_id)),
                None,
            )
            cancel_order = getattr(self, "cancel_order", None)
            if order is None or not callable(cancel_order):
                self._emit_event("ENTRY_CANCEL_FAILED", f"Cannot cancel pending {leg} entry order {order_id}")
                continue
            try:
                cancel_order(order)
                self._entry_cancel_requested_at[order_key] = time.monotonic()
                self._emit_event("ENTRY_CANCEL_REQUEST", f"Exit requested; canceling {leg} order {order_id}")
            except Exception as e:
                self._entry_cancel_requested_at.pop(order_key, None)
                logger.exception("Failed to cancel pending %s entry order before exit", leg)
                self._emit_event("ENTRY_CANCEL_FAILED", f"{leg} entry cancellation failed: {e}")
        return bool(pending)

    def _continue_exit_after_entry(self) -> None:
        """Close only confirmed entry fills after all entry orders are terminal."""
        if self._state != StrategyState.EXITING or self._entry_exit_orders_started:
            return
        if self._pending_entry_legs():
            self._cancel_pending_entry_orders()
            return

        self._entry_exit_orders_started = True
        if self._entry_fills:
            self._entry_premium = risk.entry_premium([
                (
                    fill["qty"],
                    fill["price"],
                    self._instrument_multiplier(
                        self._call_id if leg == "CALL" else self._put_id,
                    ),
                )
                for leg, fill in self._entry_fills.items()
            ])

        for leg_label, inst_id in [("CALL", self._call_id), ("PUT", self._put_id)]:
            if inst_id is None:
                continue
            pos = self._get_position(inst_id)
            fill = self._entry_fills.get(leg_label)
            if fill:
                self._exit_targets[leg_label] = fill["qty"]
            elif pos:
                self._exit_targets[leg_label] = abs(Decimal(str(pos.quantity)))
            if pos is None:
                if fill:
                    self._submit_exit_order(leg_label, inst_id, fill["qty"])
                    continue
                self._emit_event("EXIT_SKIP", f"{leg_label} already flat")
                continue
            self._submit_exit_order(leg_label, inst_id, abs(Decimal(str(pos.quantity))))
        if (
            not self._exit_orders
            and not self._entry_fills
            and not any(self._exit_targets.values())
        ):
            self._set_state(StrategyState.CLOSED)
            self._emit_event("EXIT_DONE", f"reason={self._exit_reason}; no entry fills")

    def _record_completed_trade(self) -> None:
        if not self._entry_fills or any(
            self._exit_fills.get(leg, {}).get("qty", Decimal(0)) < fill["qty"]
            for leg, fill in self._entry_fills.items()
        ):
            logger.warning("Cannot record realized PnL without confirmed entry and exit fills for every filled leg")
            return

        entry_value = sum(
            (
                fill["qty"]
                * fill["price"]
                * self._instrument_multiplier(
                    self._call_id if leg == "CALL" else self._put_id,
                )
                for leg, fill in self._entry_fills.items()
            ),
            Decimal(0),
        )
        cost = sum(
            (
                fill["qty"]
                * fill["price"]
                * self._instrument_multiplier(
                    self._call_id if leg == "CALL" else self._put_id,
                )
                for leg, fill in self._exit_fills.items()
            ),
            Decimal(0),
        )
        realized_pnl = entry_value - cost
        realized_pnl_pct = (realized_pnl / entry_value * Decimal(100)) if entry_value > 0 else Decimal(0)
        sl_th, tp_th = risk.thresholds(entry_value, self.sl_pct, self.tp_pct)
        self._last_completed_trade = {
            "entry_premium": str(entry_value),
            "exit_cost": str(cost),
            "realized_pnl": str(realized_pnl),
            "realized_pnl_pct": float(realized_pnl_pct),
            "exit_reason": getattr(self, "_exit_reason", "manual:FLATTEN"),
            "sl_threshold": str(sl_th),
            "tp_threshold": str(tp_th),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _emit_exit_wait(self, reason: str) -> None:
        now = time.monotonic()
        if reason != self._last_exit_wait_reason or now - self._last_exit_wait_ts >= 5.0:
            self._emit_event("EXIT_WAIT", reason)
            self._last_exit_wait_reason = reason
            self._last_exit_wait_ts = now

    def _cancel_active_exit_order(self, leg: str, order_id: ClientOrderId, reason: str) -> bool:
        order_key = str(order_id)
        requested_at = self._exit_cancel_requested_at.get(order_key)
        if (
            order_key in self._exit_cancel_requested
            and requested_at is not None
            and time.monotonic() - requested_at < self.cfg.exit_watchdog_secs
        ):
            return True

        order = next(
            (
                item for item in self.submitted_orders
                if str(getattr(item, "client_order_id", "")) == order_key
            ),
            None,
        )
        cancel_order = getattr(self, "cancel_order", None)
        if order is None or not callable(cancel_order):
            self._emit_event("EXIT_CANCEL_UNAVAILABLE", f"{leg} order {order_id}: cannot request cancellation")
            return False
        try:
            cancel_order(order)
            self._exit_cancel_requested.add(order_key)
            self._exit_cancel_requested_at[order_key] = time.monotonic()
            self._emit_event("EXIT_CANCEL_REQUEST", f"{leg} order {order_id}: {reason}")
            return True
        except Exception as e:
            logger.exception("Failed to cancel %s exit order %s", leg, order_id)
            self._emit_event("EXIT_CANCEL_FAILED", f"{leg} order {order_id}: {e}")
            return False

    def _submit_exit_order(self, leg_label: str, inst_id: InstrumentId, qty: Decimal) -> bool:
        """Submit at most one outstanding reduce-only close order for a leg."""
        active_id = self._active_exit_orders.get(leg_label)
        if active_id is not None:
            active_status = self._order_status.get(str(active_id), "SUBMITTED")
            if active_status not in ("FILLED", "CANCELED", "REJECTED", "DENIED"):
                return False
            self._active_exit_orders.pop(leg_label, None)

        qty = abs(Decimal(str(qty)))
        remaining = self._remaining_exit_qty(leg_label)
        if remaining is not None:
            qty = min(qty, remaining) if qty > 0 else remaining
        if qty <= 0:
            return False

        position = self._get_position(inst_id)
        side_name = self._position_side(position) if position else "SHORT"
        order_side = OrderSide.SELL if side_name == "LONG" else OrderSide.BUY
        q = self._quotes.get(str(inst_id))
        use_market = self.cfg.exit_order_style == "market"
        reference_price = Decimal(0)
        if q:
            reference_price = q["ask"] if order_side == OrderSide.BUY else q["bid"]
        quote_is_fresh = (
            q is not None
            and time.time() - q["timestamp"] <= self.cfg.stale_quote_secs
            and not q.get("is_synthetic")
            and reference_price > 0
        )
        if not use_market and not quote_is_fresh:
            self._emit_exit_wait(
                f"Waiting for a fresh executable {'ask' if order_side == OrderSide.BUY else 'bid'} "
                f"before closing {leg_label}",
            )
            return False

        if leg_label not in self._exit_targets:
            self._exit_targets[leg_label] = qty
        quantity = Quantity.from_str(str(qty))
        inst = self.cache.instrument(inst_id) if getattr(self, "cache", None) is not None else None
        order_qty = inst.make_qty(qty) if inst else quantity
        actual_qty = abs(Decimal(str(order_qty)))
        if actual_qty <= 0:
            self._emit_event("EXIT_SUBMIT_FAILED", f"{leg_label} close quantity is below instrument precision")
            return False

        order_price = None
        if not use_market:
            tick_sz = inst.price_increment.as_double() if inst and hasattr(inst, "price_increment") else 5.0
            buffered_price = (
                reference_price * (Decimal(1) + _ASK_BUFFER_PCT)
                if order_side == OrderSide.BUY
                else reference_price * (Decimal(1) - _ASK_BUFFER_PCT)
            )
            rounding = ROUND_CEILING if order_side == OrderSide.BUY else ROUND_FLOOR
            prec = inst.price_precision if inst and hasattr(inst, "price_precision") else None
            order_price = _quantize_price(buffered_price, tick_sz, rounding, precision=prec)

        if self.order_factory is not None:
            if use_market:
                order = self.order_factory.market(
                    instrument_id=inst_id,
                    order_side=order_side,
                    quantity=order_qty,
                    time_in_force=TimeInForce.IOC,
                    reduce_only=True,
                )
            else:
                order = self.order_factory.limit(
                    instrument_id=inst_id,
                    order_side=order_side,
                    quantity=order_qty,
                    price=order_price,
                    time_in_force=TimeInForce.IOC,
                    reduce_only=True,
                )
        else:
            from types import SimpleNamespace

            coid = ClientOrderId(f"O-EXIT-{leg_label}-{int(time.time() * 1000)}")
            order = SimpleNamespace(
                client_order_id=coid,
                instrument_id=inst_id,
                order_side=order_side,
                quantity=order_qty,
                price=order_price,
                reduce_only=True,
            )

        coid = order.client_order_id
        order_key = str(coid)
        self.submitted_orders.append(order)
        self._exit_orders[leg_label] = coid
        self._exit_order_legs[order_key] = leg_label
        self._active_exit_orders[leg_label] = coid
        self._order_status[order_key] = "SUBMITTED"
        self._order_submitted_at[order_key] = datetime.now(timezone.utc).isoformat()
        self._order_submitted_monotonic[order_key] = time.monotonic()
        self._order_target_qty[order_key] = actual_qty
        self._order_sides[order_key] = str(order_side).replace("OrderSide.", "")

        try:
            if self.order_factory is not None:
                self.submit_order(order)
        except Exception as e:
            logger.exception("Failed to submit %s exit order", leg_label)
            self._order_status[order_key] = "REJECTED"
            if leg_label in self._active_exit_orders and self._active_exit_orders[leg_label] == coid:
                self._active_exit_orders.pop(leg_label, None)
            self._emit_event("ORDER_SUBMIT_FAILED", f"{leg_label} exit submission failed: {e}")
            self._publish_snapshot()
            return False

        self._emit_event(
            "EXIT_SUBMIT",
            f"{leg_label} side={order_side} qty={actual_qty} "
            f"price={order_price if order_price is not None else 'MARKET'} order={coid}",
        )
        self._publish_snapshot()
        return True

    def _check_exit_complete(self) -> None:
        """Move to CLOSED if both positions are flat."""
        if self._state != StrategyState.EXITING:
            return
        for inst_id in (self._call_id, self._put_id):
            if inst_id and self._get_position(inst_id):
                return
        for leg, fill in self._entry_fills.items():
            if self._exit_fills.get(leg, {}).get("qty", Decimal(0)) < fill["qty"]:
                return
        self._record_completed_trade()
        self._set_state(StrategyState.CLOSED)
        self._emit_event("EXIT_DONE", f"reason={self._exit_reason}")

    # ── order events ───────────────────────────────────────────────────
    def on_order_filled(self, event: OrderFilled) -> None:
        oid = event.client_order_id
        order_key = str(oid)
        leg = self._order_to_leg(oid)
        if leg is None:
            return

        is_entry = order_key in self._entry_order_legs
        is_exit = order_key in self._exit_order_legs

        if is_entry:
            fill_qty = Decimal(str(event.last_qty))
            fill_price = Decimal(str(event.last_px))
            if fill_qty <= 0 or fill_price <= 0:
                self._emit_event("WARN", f"Ignoring invalid {leg} entry fill qty={fill_qty} px={fill_price}")
                return
            previous_status = self._order_status.get(order_key, "")
            self._record_order_fill(oid, fill_qty, fill_price)
            self._accumulate_fill(self._entry_fills, leg, fill_qty, fill_price)
            self._emit_event("ENTRY_FILL", f"{leg} qty={event.last_qty} px={event.last_px}")
            if self._state == StrategyState.EXITING:
                self._exit_targets[leg] = max(
                    self._exit_targets.get(leg, Decimal(0)),
                    self._entry_fills[leg]["qty"],
                )

            # Keep current-run execution history separate from strategy events.
            bridge.push_event({
                "type": "order_fill",
                "leg": leg,
                "client_order_id": order_key,
                "instrument_id": str(event.instrument_id or (
                    self._call_id if leg == "CALL" else self._put_id
                )),
                "side": "SELL",
                "qty": str(event.last_qty),
                "price": str(event.last_px),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            target_qty = self._entry_targets.get(leg, Decimal(str(self.qty)))
            if self._entry_fills[leg]["qty"] >= target_qty:
                self._entry_terminal_legs.add(leg)
            order_target = self._order_target_qty.get(order_key, target_qty)
            order_filled = self._order_fills[order_key]["qty"]
            if order_filled >= order_target:
                self._order_status[order_key] = "FILLED"
                self._entry_cancel_requested_at.pop(order_key, None)
            elif previous_status not in ("CANCELED", "REJECTED", "DENIED"):
                self._order_status[order_key] = "PARTIALLY_FILLED"

            if (
                previous_status in ("CANCELED", "REJECTED", "DENIED")
                or self._state in (
                    StrategyState.IDLE,
                    StrategyState.SELECTED,
                    StrategyState.QUOTING,
                    StrategyState.CLOSED,
                )
            ):
                self._entry_terminal_legs.add(leg)
                if self._state != StrategyState.EXITING:
                    self._exit_reason = f"late_entry_fill:{leg}"
                    self._exit_orders = {}
                    self._active_exit_orders = {}
                    self._exit_cancel_requested = set()
                    self._exit_cancel_requested_at = {}
                    self._exit_fills = {}
                    self._exit_targets = {}
                    self._exit_retries = {"CALL": 0, "PUT": 0}
                    self._entry_exit_orders_started = False
                    self._set_state(StrategyState.EXITING)
                self._cancel_pending_entry_orders()
                self._continue_exit_after_entry()
                self._publish_snapshot()
                return

            if all(
                self._entry_fills.get(entry_leg, {}).get("qty", Decimal(0))
                >= self._entry_targets.get(entry_leg, Decimal(str(self.qty)))
                for entry_leg in ("CALL", "PUT")
            ):
                if self._state == StrategyState.EXITING:
                    self._continue_exit_after_entry()
                else:
                    legs_data = []
                    for l in ("CALL", "PUT"):
                        f = self._entry_fills[l]
                        inst_id = self._call_id if l == "CALL" else self._put_id
                        legs_data.append((
                            f["qty"],
                            f["price"],
                            self._instrument_multiplier(inst_id),
                        ))
                    self._entry_premium = risk.entry_premium(legs_data)
                    self._set_state(StrategyState.OPEN)
                    self._emit_event("ENTRY_COMPLETE", f"entry_premium={self._entry_premium}")
            elif self._state == StrategyState.EXITING:
                self._continue_exit_after_entry()
            elif any(entry_leg in self._entry_terminal_legs for entry_leg in ("CALL", "PUT")):
                other_leg = "PUT" if leg == "CALL" else "CALL"
                if other_leg in self._entry_terminal_legs:
                    self._handle_entry_leg_failure(other_leg)
            if self._state == StrategyState.EXITING and not self._pending_entry_legs():
                if self._entry_exit_orders_started:
                    self._retry_exit_leg(leg)
                else:
                    self._continue_exit_after_entry()

        elif is_exit:
            fill_qty = Decimal(str(event.last_qty))
            fill_price = Decimal(str(event.last_px))
            if fill_qty <= 0 or fill_price <= 0:
                self._emit_event("WARN", f"Ignoring invalid {leg} exit fill qty={fill_qty} px={fill_price}")
                return
            previous_status = self._order_status.get(order_key, "")
            self._record_order_fill(oid, fill_qty, fill_price)
            self._accumulate_fill(self._exit_fills, leg, fill_qty, fill_price)
            order_target = self._order_target_qty.get(order_key)
            order_filled = self._order_fills[order_key]["qty"]
            if order_target is not None and order_filled >= order_target:
                self._order_status[order_key] = "FILLED"
            elif previous_status not in ("CANCELED", "REJECTED", "DENIED"):
                self._order_status[order_key] = "PARTIALLY_FILLED"
            self._emit_event("EXIT_FILL", f"{leg} qty={event.last_qty} px={event.last_px}")
            bridge.push_event({
                "type": "order_fill",
                "leg": leg,
                "client_order_id": order_key,
                "instrument_id": str(event.instrument_id or (
                    self._call_id if leg == "CALL" else self._put_id
                )),
                "side": self._order_sides.get(order_key, "BUY"),
                "qty": str(event.last_qty),
                "price": str(event.last_px),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            remaining = self._remaining_exit_qty(leg)
            active_id = self._active_exit_orders.get(leg)
            if active_id is not None and active_id == oid and self._order_status[order_key] == "FILLED":
                self._active_exit_orders.pop(leg, None)
                self._exit_cancel_requested.discard(order_key)
                self._exit_cancel_requested_at.pop(order_key, None)
                self._entry_cancel_requested_at.pop(order_key, None)
            elif active_id is not None and active_id != oid and remaining is not None:
                self._cancel_active_exit_order(
                    leg,
                    active_id,
                    "another confirmed fill changed the remaining close quantity",
                )
            if remaining == 0 and active_id is not None and active_id != oid:
                self._cancel_active_exit_order(leg, active_id, "position is already fully bought back")
            self._check_exit_complete()
            if (
                self._state == StrategyState.EXITING
                and self._order_status.get(order_key) == "FILLED"
                and self._active_exit_orders.get(leg) is None
            ):
                self._retry_exit_leg(leg)

        self._publish_snapshot()

    def on_order_rejected(self, event: OrderRejected) -> None:
        oid = event.client_order_id
        order_key = str(oid)
        leg = self._order_to_leg(oid)
        self._order_status[order_key] = "REJECTED"
        self._emit_event("ORDER_REJECTED", f"leg={leg} order={oid} reason={event.reason}")
        if leg in self._active_exit_orders and self._active_exit_orders[leg] == oid:
            self._active_exit_orders.pop(leg, None)
        self._exit_cancel_requested.discard(order_key)
        self._exit_cancel_requested_at.pop(order_key, None)
        self._entry_cancel_requested_at.pop(order_key, None)

        if order_key in self._entry_order_legs and leg:
            if self._state == StrategyState.EXITING:
                self._entry_terminal_legs.add(leg)
                self._continue_exit_after_entry()
            else:
                self._handle_entry_leg_failure(leg)
        elif order_key in self._exit_order_legs and leg:
            self._retry_exit_leg(leg)
        self._publish_snapshot()

    def on_order_denied(self, event: OrderDenied) -> None:
        oid = event.client_order_id
        order_key = str(oid)
        leg = self._order_to_leg(oid)
        self._order_status[order_key] = "DENIED"
        self._emit_event("ORDER_DENIED", f"leg={leg} order={oid} reason={event.reason}")
        if leg in self._active_exit_orders and self._active_exit_orders[leg] == oid:
            self._active_exit_orders.pop(leg, None)
        self._exit_cancel_requested.discard(order_key)
        self._exit_cancel_requested_at.pop(order_key, None)
        self._entry_cancel_requested_at.pop(order_key, None)

        if order_key in self._entry_order_legs and leg:
            if self._state == StrategyState.EXITING:
                self._entry_terminal_legs.add(leg)
                self._continue_exit_after_entry()
            else:
                self._handle_entry_leg_failure(leg)
        elif order_key in self._exit_order_legs and leg:
            self._retry_exit_leg(leg)
        self._publish_snapshot()

    def on_order_canceled(self, event: OrderCanceled) -> None:
        oid = event.client_order_id
        order_key = str(oid)
        leg = self._order_to_leg(oid)
        is_entry = order_key in self._entry_order_legs
        is_exit = order_key in self._exit_order_legs

        self._order_status[order_key] = "CANCELED"
        self._emit_event("ORDER_CANCELED", f"leg={leg} order={oid}")
        if leg in self._active_exit_orders and self._active_exit_orders[leg] == oid:
            self._active_exit_orders.pop(leg, None)
        self._exit_cancel_requested.discard(order_key)
        self._exit_cancel_requested_at.pop(order_key, None)
        self._entry_cancel_requested_at.pop(order_key, None)

        if is_entry and leg and self._state == StrategyState.EXITING:
            self._entry_terminal_legs.add(leg)
            self._continue_exit_after_entry()
        elif is_entry and leg and self._state != StrategyState.OPEN:
            self._handle_entry_leg_failure(leg)

        if is_exit and leg and self._state == StrategyState.EXITING:
            self._retry_exit_leg(leg)
        self._publish_snapshot()

    def on_order_accepted(self, event: OrderAccepted) -> None:
        oid = event.client_order_id
        order_key = str(oid)
        if self._order_status.get(order_key) not in (
            "FILLED",
            "PARTIALLY_FILLED",
            "CANCELED",
            "REJECTED",
            "DENIED",
        ):
            self._order_status[order_key] = "ACCEPTED"
        self._publish_snapshot()

    def _retry_exit_leg(self, leg: str) -> None:
        if self._state != StrategyState.EXITING:
            return
        inst_id = self._call_id if leg == "CALL" else self._put_id
        if inst_id is None:
            return

        active_id = self._active_exit_orders.get(leg)
        if active_id is not None:
            active_status = self._order_status.get(str(active_id), "SUBMITTED")
            if active_status not in ("FILLED", "CANCELED", "REJECTED", "DENIED"):
                return
            self._active_exit_orders.pop(leg, None)

        pos = self._get_position(inst_id) if inst_id else None
        remaining = self._remaining_exit_qty(leg)
        if remaining is not None and remaining <= 0:
            self._check_exit_complete()
            return
        if pos is None and remaining is None:
            self._check_exit_complete()
            return

        qty = remaining if pos is None else abs(Decimal(str(pos.quantity)))
        if remaining is not None:
            qty = min(qty, remaining)
        retries = self._exit_retries.get(leg, 0)
        if retries >= _EXIT_MAX_RETRIES:
            self._emit_event("EXIT_RETRY_EXHAUSTED", f"{leg} after {retries} retries")
            return
        if self._submit_exit_order(leg, inst_id, qty):
            self._exit_retries[leg] = retries + 1

    def _handle_entry_leg_failure(self, failed_leg: str) -> None:
        """Cancel the other entry leg and unwind any confirmed partial entry fills."""
        self._entry_terminal_legs.add(failed_leg)
        other_leg = "PUT" if failed_leg == "CALL" else "CALL"
        other_order = self._entry_orders.get(other_leg)
        other_fill = self._entry_fills.get(other_leg, {}).get("qty", Decimal(0))
        other_target = self._entry_targets.get(other_leg, Decimal(str(self.qty)))

        if other_order and other_fill < other_target and other_leg not in self._entry_terminal_legs:
            order = next(
                (item for item in self.submitted_orders
                 if str(getattr(item, "client_order_id", "")) == str(other_order)),
                None,
            )
            cancel_order = getattr(self, "cancel_order", None)
            if order is not None and callable(cancel_order):
                try:
                    cancel_order(order)
                    self._emit_event("ENTRY_CANCEL_REQUEST", f"Cancel requested for {other_leg} order {other_order}")
                except Exception as e:
                    logger.exception("Failed to cancel pending %s entry order", other_leg)
                    self._emit_event("ORDER_CANCEL_FAILED", f"{other_leg} entry cancellation failed: {e}")

        all_legs_terminal = all(
            leg in self._entry_terminal_legs
            or self._entry_fills.get(leg, {}).get("qty", Decimal(0))
            >= self._entry_targets.get(leg, Decimal(str(self.qty)))
            for leg in ("CALL", "PUT")
        )
        if not all_legs_terminal:
            return

        has_fills = any(fill.get("qty", Decimal(0)) > 0 for fill in self._entry_fills.values())
        has_positions = any(self._get_position(inst_id) for inst_id in (self._call_id, self._put_id) if inst_id)
        if not has_fills and not has_positions:
            self._set_state(StrategyState.QUOTING)
            self._emit_event("ENTRY_FAIL", f"{failed_leg} entry failed without fills; returned to QUOTING")
            return

        self._exit_reason = f"entry_failure:{failed_leg}"
        self._exit_orders = {}
        self._active_exit_orders = {}
        self._exit_cancel_requested = set()
        self._exit_fills = {}
        self._exit_retries = {"CALL": 0, "PUT": 0}
        self._exit_targets = {}
        self._entry_exit_orders_started = True
        self._set_state(StrategyState.EXITING)
        self._emit_event("UNWIND", f"Unwinding confirmed partial entry after {failed_leg} failed")

        for leg, inst_id in (("CALL", self._call_id), ("PUT", self._put_id)):
            if inst_id is None:
                continue
            pos = self._get_position(inst_id)
            fill = self._entry_fills.get(leg)
            qty = abs(Decimal(str(pos.quantity))) if pos else (fill["qty"] if fill else Decimal(0))
            if qty > 0:
                self._exit_targets[leg] = fill["qty"] if fill else qty
                self._submit_exit_order(leg, inst_id, qty)

    def _order_to_leg(self, oid: ClientOrderId) -> str | None:
        """Map a ClientOrderId back to 'CALL' or 'PUT'."""
        order_key = str(oid)
        return self._entry_order_legs.get(order_key) or self._exit_order_legs.get(order_key)

    # ── commands (timer callback) ──────────────────────────────────────
    def _on_drain_timer(self, event) -> None:
        """Timer callback: drain commands from the bridge."""
        for cmd in bridge.drain_commands():
            self._handle_command(cmd)

    def _handle_command(self, cmd: dict) -> None:
        command = cmd.get("command", "").upper()
        self._emit_event("COMMAND", f"Received {command}")

        if command == "ARM":
            # Clear old fills and tracking for a new straddle trade cycle
            self._entry_fills = {}
            self._entry_orders = {}
            self._entry_order_legs = {}
            self._entry_targets = {}
            self._entry_terminal_legs = set()
            self._exit_orders = {}
            self._exit_order_legs = {}
            self._active_exit_orders = {}
            self._exit_cancel_requested = set()
            self._exit_cancel_requested_at = {}
            self._exit_targets = {}
            self._exit_fills = {}
            self._exit_retries = {}
            self._entry_cancel_requested_at = {}
            self._entry_exit_orders_started = False
            self._last_completed_trade = None
            if self._state in (StrategyState.QUOTING, StrategyState.SELECTED, StrategyState.IDLE, StrategyState.CLOSED):
                if self._call_id is None or self._put_id is None or self._is_selection_expired():
                    instruments = self._fetch_and_cache_bybit_instruments()
                    if instruments:
                        self._run_selector(instruments)
                self._set_state(StrategyState.ARMED)
                self._attempt_entry()
            elif self._state == StrategyState.ARMED:
                self._attempt_entry()
            else:
                self._emit_event("WARN", f"Cannot ARM in state {self._state.value}")

        elif command == "DISARM":
            if self._state == StrategyState.ARMED:
                self._set_state(StrategyState.QUOTING)
                self._emit_event("INFO", "Strategy DISARMED to QUOTING")
            elif self._state == StrategyState.ENTRY_SUBMITTED:
                pending = [
                    leg for leg in ("CALL", "PUT")
                    if self._entry_fills.get(leg, {}).get("qty", Decimal(0))
                    < self._entry_targets.get(leg, Decimal(str(self.qty)))
                    and leg not in self._entry_terminal_legs
                ]
                if not pending:
                    self._emit_event("WARN", "Cannot DISARM: both entry legs have filled")
                else:
                    for leg in pending:
                        order_id = self._entry_orders.get(leg)
                        order = next(
                            (item for item in self.submitted_orders
                             if str(getattr(item, "client_order_id", "")) == str(order_id)),
                            None,
                        )
                        cancel_order = getattr(self, "cancel_order", None)
                        if order is not None and callable(cancel_order):
                            try:
                                cancel_order(order)
                                self._emit_event("ENTRY_CANCEL_REQUEST", f"Disarm requested; canceling {leg} order")
                            except Exception as e:
                                logger.exception("Failed to cancel %s entry order during disarm", leg)
                                self._emit_event("ORDER_CANCEL_FAILED", f"{leg} entry cancellation failed: {e}")
                    self._emit_event("INFO", "Disarm requested; waiting for exchange order confirmations")
            elif self._state == StrategyState.QUOTING:
                self._emit_event("INFO", "Strategy is already in QUOTING (DISARMED)")
            else:
                self._emit_event("WARN", f"Cannot DISARM in state {self._state.value}")

        elif command == "FLATTEN":
            if self._state in (StrategyState.OPEN, StrategyState.UNBALANCED, StrategyState.ARMED, StrategyState.ENTRY_SUBMITTED, StrategyState.EXITING):
                self._exit_retries.clear()
                self._request_exit("manual:FLATTEN")
            else:
                self._emit_event("WARN", f"Cannot FLATTEN in state {self._state.value}")

        elif command == "RESET":
            self._handle_reset()

        elif command == "UPDATE_CONFIG":
            payload = cmd.get("payload", {})
            if self._state in (StrategyState.OPEN, StrategyState.ENTRY_SUBMITTED, StrategyState.EXITING):
                self._emit_event("WARN", "Cannot update config while position is open")
            else:
                if "sl_pct" in payload and payload["sl_pct"] is not None:
                    self._sl_pct = float(payload["sl_pct"])
                if "tp_pct" in payload and payload["tp_pct"] is not None:
                    self._tp_pct = float(payload["tp_pct"])
                if "qty" in payload and payload["qty"] is not None:
                    self._qty = float(payload["qty"])
                if "max_spread_pct" in payload and payload["max_spread_pct"] is not None:
                    self._max_spread_pct = float(payload["max_spread_pct"])
                self._emit_event("CONFIG_UPDATED", str(payload))
                self._publish_snapshot()
                if self._state == StrategyState.ARMED:
                    self._attempt_entry()

    def _handle_reset(self) -> None:
        """Emergency reset: cancels pending orders, market-flattens open positions, and returns to QUOTING."""
        logger.info("Handling emergency RESET command")
        cancel_order = getattr(self, "cancel_order", None)
        if callable(cancel_order):
            for order in list(getattr(self, "submitted_orders", [])):
                oid = getattr(order, "client_order_id", None)
                if oid:
                    status = self._order_status.get(str(oid), "")
                    if status not in ("FILLED", "CANCELED", "REJECTED", "DENIED"):
                        try:
                            cancel_order(order)
                        except Exception:
                            pass

        for leg_label, inst_id in [("CALL", self._call_id), ("PUT", self._put_id)]:
            if inst_id is None:
                continue
            pos = self._get_position(inst_id)
            if pos:
                qty = abs(Decimal(str(pos.quantity)))
                if qty > 0 and self.order_factory is not None:
                    try:
                        inst = self.cache.instrument(inst_id) if getattr(self, "cache", None) else None
                        order_qty = inst.make_qty(qty) if inst else Quantity.from_str(str(qty))
                        side_name = self._position_side(pos)
                        order_side = OrderSide.SELL if side_name == "LONG" else OrderSide.BUY
                        order = self.order_factory.market(
                            instrument_id=inst_id,
                            order_side=order_side,
                            quantity=order_qty,
                            reduce_only=True,
                        )
                        self.submit_order(order)
                    except Exception as e:
                        logger.warning("Failed to submit market close during reset for %s: %s", leg_label, e)

        self._exit_retries.clear()
        self._active_exit_orders.clear()
        self._entry_terminal_legs.clear()
        self._entry_fills.clear()
        self._exit_fills.clear()
        self._exit_targets.clear()
        self._last_completed_trade = None
        self._entry_exit_orders_started = False

        try:
            instruments = self._fetch_and_cache_bybit_instruments()
            if instruments:
                self._run_selector(instruments)
        except Exception as e:
            logger.debug("Selector re-run on reset notice: %s", e)

        self._set_state(StrategyState.QUOTING)
        self._emit_event("RESET", "Strategy forcibly reset to QUOTING state")
        self._publish_snapshot()

    # ── watchdog ───────────────────────────────────────────────────────
    def _on_watchdog(self, event) -> None:
        """Periodic safety checks."""
        # 0. If in IDLE and not yet selected, or selection is expired, retry running selector on cache instruments
        selection_expired = self._is_selection_expired()
        if (
            (self._state in (StrategyState.IDLE, StrategyState.QUOTING, StrategyState.ARMED)
             and (self._selection is None or getattr(self._selection, "reason", None) or selection_expired))
            and not (self._call_id and self._get_position(self._call_id))
            and not (self._put_id and self._get_position(self._put_id))
        ):
            try:
                instruments = self._fetch_and_cache_bybit_instruments()
                if instruments:
                    self._run_selector(instruments)
            except Exception as e:
                logger.debug("Selector retry in watchdog: %s", e)

        # If ARMED and auto_enter, keep trying
        if self._state == StrategyState.ARMED and self.cfg.auto_enter:
            self._attempt_entry()

        if self._state == StrategyState.ENTRY_SUBMITTED:
            for failed_leg in tuple(self._entry_terminal_legs):
                self._handle_entry_leg_failure(failed_leg)
                break
            now = time.monotonic()
            stalled = False
            for leg in self._pending_entry_legs():
                order_key = str(self._entry_orders.get(leg))
                submitted_at = self._order_submitted_monotonic.get(order_key, now)
                cancel_requested_at = self._entry_cancel_requested_at.get(order_key)
                if (
                    now - submitted_at >= self.cfg.exit_watchdog_secs
                    and (
                        cancel_requested_at is None
                        or now - cancel_requested_at >= self.cfg.exit_watchdog_secs
                    )
                ):
                    stalled = True
                    break
            if stalled:
                self._emit_event(
                    "ENTRY_WATCHDOG",
                    "Entry IOC acknowledgement timed out; requesting cancellation and reconciliation",
                )
                self._cancel_pending_entry_orders()

        # Never submit a replacement while the exchange may still fill the old order.
        if self._state == StrategyState.EXITING:
            if self._pending_entry_legs():
                self._cancel_pending_entry_orders()
                return
            for leg_label in ("CALL", "PUT"):
                active_id = self._active_exit_orders.get(leg_label)
                if active_id is not None:
                    order_key = str(active_id)
                    status = self._order_status.get(order_key, "SUBMITTED")
                    if status in ("FILLED", "CANCELED", "REJECTED", "DENIED"):
                        self._active_exit_orders.pop(leg_label, None)
                        self._exit_cancel_requested.discard(order_key)
                    else:
                        submitted_at = self._order_submitted_monotonic.get(
                            order_key,
                            time.monotonic(),
                        )
                        if time.monotonic() - submitted_at >= self.cfg.exit_watchdog_secs:
                            self._cancel_active_exit_order(
                                leg_label,
                                active_id,
                                "exit order exceeded watchdog timeout",
                            )
                        continue
                self._retry_exit_leg(leg_label)
            self._check_exit_complete()

    # ── events ─────────────────────────────────────────────────────────
    def _emit_event(self, code: str, text: str) -> None:
        self._event_seq += 1
        evt = {
            "type": "event",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "INFO" if code not in ("WARN", "ORDER_REJECTED", "ORDER_DENIED", "EXIT_RETRY_EXHAUSTED") else "WARNING",
            "code": code,
            "text": text,
            "seq": self._event_seq,
        }
        bridge.push_event(evt)
        logger.info("[%s] %s", code, text)

    # ── snapshot ───────────────────────────────────────────────────────
    def _build_snapshot(self) -> dict[str, Any]:
        positions = []
        for leg_label, inst_id in [("CALL", self._call_id), ("PUT", self._put_id)]:
            if inst_id is None:
                continue
            pos = self._get_position(inst_id)
            if pos:
                q = self._quotes.get(str(inst_id))
                positions.append({
                    "instrument_id": str(inst_id),
                    "leg": leg_label,
                    "side": str(pos.side) if hasattr(pos, "side") else "SELL",
                    "qty": str(pos.quantity),
                    "avg_entry": str(pos.avg_px_open) if hasattr(pos, "avg_px_open") else "0",
                    "current_bid": str(q["bid"]) if q else "0",
                    "current_ask": str(q["ask"]) if q else "0",
                    "multiplier": str(self._instrument_multiplier(inst_id)),
                })
            elif self._state == StrategyState.OPEN and leg_label in self._entry_fills:
                fill = self._entry_fills[leg_label]
                q = self._quotes.get(str(inst_id))
                positions.append({
                    "instrument_id": str(inst_id),
                    "leg": leg_label,
                    "side": "SELL",
                    "qty": str(fill["qty"]),
                    "avg_entry": str(fill["price"]),
                    "current_bid": str(q["bid"]) if q else "0",
                    "current_ask": str(q["ask"]) if q else "0",
                    "multiplier": str(self._instrument_multiplier(inst_id)),
                })

        # risk metrics
        risk_info = None
        cq = self._quotes.get(str(self._call_id)) if self._call_id else None
        pq = self._quotes.get(str(self._put_id)) if self._put_id else None

        if (
            self._state == StrategyState.OPEN
            and self._call_id and self._put_id and cq and pq
            and self._quotes_fresh()
            and not cq.get("is_synthetic")
            and not pq.get("is_synthetic")
            and cq["ask"] > 0
            and pq["ask"] > 0
        ):
            asks = [cq["ask"], pq["ask"]]
            call_qty = self._entry_fills.get("CALL", {}).get("qty", Decimal(str(self.qty)))
            put_qty = self._entry_fills.get("PUT", {}).get("qty", Decimal(str(self.qty)))
            cost = risk.buyback_cost(
                [
                    (call_qty, asks[0], self._instrument_multiplier(self._call_id)),
                    (put_qty, asks[1], self._instrument_multiplier(self._put_id)),
                ],
                asks,
            )
            sl_th, tp_th = risk.thresholds(self._entry_premium, self.sl_pct, self.tp_pct)
            bids = [cq["bid"], pq["bid"]]
            sp = risk.spread_pct(bids, asks)
            risk_info = {
                "is_live": True,
                "state": "OPEN",
                "entry_premium": str(self._entry_premium),
                "buyback_cost": str(cost),
                "sl_threshold": str(sl_th),
                "tp_threshold": str(tp_th),
                "spread_pct": float(sp),
            }
        elif self._state == StrategyState.CLOSED and getattr(self, "_last_completed_trade", None):
            last = self._last_completed_trade
            risk_info = {
                "is_live": False,
                "state": "CLOSED",
                "entry_premium": last["entry_premium"],
                "buyback_cost": last["exit_cost"],
                "realized_pnl": last["realized_pnl"],
                "realized_pnl_pct": last["realized_pnl_pct"],
                "exit_reason": last["exit_reason"],
                "sl_threshold": last["sl_threshold"],
                "tp_threshold": last["tp_threshold"],
                "spread_pct": 0.01,
            }
        elif (
            self._call_id and self._put_id and cq and pq
            and not cq.get("is_synthetic")
            and not pq.get("is_synthetic")
        ):
            bids = [cq.get("bid", Decimal(0)), pq.get("bid", Decimal(0))]
            asks = [cq.get("ask", Decimal(0)), pq.get("ask", Decimal(0))]
            qty = Decimal(str(self.qty))
            call_multiplier = self._instrument_multiplier(self._call_id)
            put_multiplier = self._instrument_multiplier(self._put_id)
            proj_entry = (
                bids[0] * qty * call_multiplier
                + bids[1] * qty * put_multiplier
            )
            proj_cost = (
                asks[0] * qty * call_multiplier
                + asks[1] * qty * put_multiplier
            )
            sl_th, tp_th = risk.thresholds(proj_entry, self.sl_pct, self.tp_pct)
            if proj_entry > 0 and all(price > 0 for price in bids + asks):
                sp = risk.spread_pct(bids, asks)
                risk_info = {
                    "is_live": False,
                    "state": self._state.value,
                    "entry_premium": str(proj_entry),
                    "buyback_cost": str(proj_cost),
                    "sl_threshold": str(sl_th),
                    "tp_threshold": str(tp_th),
                    "spread_pct": float(sp),
                }

        # Structured quotes for frontend
        now_ts = time.time()
        call_q = self._quotes.get(str(self._call_id)) if self._call_id else None
        put_q = self._quotes.get(str(self._put_id)) if self._put_id else None

        def _format_quote(q):
            if not q:
                return None
            ts = q.get("timestamp", now_ts)
            age_ms = int(max(0, (now_ts - ts) * 1000))
            return {
                "bid": float(q["bid"]),
                "ask": float(q["ask"]),
                "bid_size": float(q["bid_size"]),
                "ask_size": float(q["ask_size"]),
                "timestamp": ts,
                "age_ms": age_ms,
                "is_synthetic": bool(q.get("is_synthetic")),
            }

        quotes_dict = {k: {qk: str(qv) if isinstance(qv, Decimal) else qv for qk, qv in v.items()} for k, v in self._quotes.items()}
        quotes_dict["call"] = _format_quote(call_q)
        quotes_dict["put"] = _format_quote(put_q)

        # Orders list
        orders_list = []
        for o in getattr(self, "submitted_orders", []):
            cid = getattr(o, "client_order_id", "")
            order_key = str(cid)
            inst = getattr(o, "instrument_id", "")
            side = getattr(o, "order_side", getattr(o, "side", "SELL"))
            qty = getattr(o, "quantity", 0)
            px = getattr(o, "price", 0)
            fill = self._order_fills.get(
                order_key,
                {"qty": Decimal(0), "avg_price": Decimal(0)},
            )
            orders_list.append({
                "order_id": order_key,
                "instrument_id": str(inst),
                "leg": self._order_to_leg(cid),
                "side": str(side).replace("OrderSide.", ""),
                "type": "LIMIT" if px else "MARKET",
                "qty": str(qty),
                "price": str(px) if px else "MARKET",
                "status": self._order_status.get(str(cid), "UNKNOWN"),
                "filled_qty": str(fill["qty"]),
                "avg_price": str(fill["avg_price"]) if fill["qty"] > 0 else None,
                "timestamps": {"submitted": self._order_submitted_at.get(str(cid))},
            })

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "state": self._state.value,
            "mode": getattr(settings, "BYBIT_ENVIRONMENT", "TESTNET").lower(),
            "selection": {
                "expiry": self._selection.expiry.isoformat() if self._selection and self._selection.expiry else None,
                "strike": str(self._selection.strike) if self._selection else None,
                "call_id": self._selection.call_id if self._selection else None,
                "put_id": self._selection.put_id if self._selection else None,
                "ref_price": str(self._selection.ref_price) if self._selection else None,
            } if self._selection else None,
            "quotes": quotes_dict,
            "risk": risk_info,
            "positions": positions,
            "orders": orders_list,
            "entry_premium": str(self._entry_premium),
            "last_completed_trade": getattr(self, "_last_completed_trade", None),
            "config": {
                "sl_pct": self.sl_pct,
                "tp_pct": self.tp_pct,
                "qty": self.qty,
                "max_spread_pct": self.max_spread_pct,
                "entry_order_style": self.cfg.entry_order_style,
                "exit_order_style": self.cfg.exit_order_style,
                "leg_fail_policy": self.cfg.leg_fail_policy,
                "auto_enter": self.cfg.auto_enter,
            },
        }
