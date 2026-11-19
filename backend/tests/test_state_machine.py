"""Tests for StraddleStrategy state machine transitions and command handling."""

from __future__ import annotations

import time
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest

from backend.models import StrategyState, SelectionResult
from backend.strategy import (
    StraddleStrategy,
    StraddleConfig,
    InstrumentId,
    ClientOrderId,
    OrderSide,
    TimeInForce,
    QuoteTick,
    Position,
    OrderFilled,
    OrderRejected,
    OrderCanceled,
)
from backend.bridge import bridge


class MockPosition:
    def __init__(self, instrument_id, quantity):
        self.instrument_id = instrument_id
        self.quantity = quantity


class MockEvent:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def create_strategy(max_spread_pct=0.05):
    cfg = StraddleConfig(
        sl_pct=0.01,
        tp_pct=0.02,
        qty=0.01,
        max_spread_pct=max_spread_pct,
        stale_quote_secs=10,
        exit_watchdog_secs=10,
        auto_enter=False,
        entry_order_style="ioc_limit",
        exit_order_style="ioc_limit",
        leg_fail_policy="unwind",
    )
    strat = StraddleStrategy(config=cfg)

    # Set up dummy selection
    call_id = "BTC-28MAR26-70000-C-USDT.BYBIT"
    put_id = "BTC-28MAR26-70000-P-USDT.BYBIT"
    strat._call_id = InstrumentId.from_str(call_id)
    strat._put_id = InstrumentId.from_str(put_id)
    strat._selection = SelectionResult(
        expiry=datetime.now(timezone.utc),
        strike=Decimal("70000"),
        call_id=call_id,
        put_id=put_id,
        ref_price=Decimal("70000"),
    )
    # Put fresh quotes
    now_ts = time.time()
    strat._quotes[call_id] = {
        "instrument_id": call_id,
        "bid": Decimal("1000"),
        "ask": Decimal("1010"),
        "bid_size": Decimal("1.0"),
        "ask_size": Decimal("1.0"),
        "timestamp": now_ts,
    }
    strat._quotes[put_id] = {
        "instrument_id": put_id,
        "bid": Decimal("900"),
        "ask": Decimal("910"),
        "bid_size": Decimal("1.0"),
        "ask_size": Decimal("1.0"),
        "timestamp": now_ts,
    }
    return strat


def test_initial_state():
    strat = create_strategy()
    assert strat.state == StrategyState.IDLE


def test_arm_command_transitions_to_entry_submitted():
    strat = create_strategy()
    strat._set_state(StrategyState.QUOTING)

    # Dispatch ARM command
    strat._handle_command({"command": "ARM"})
    assert strat.state == StrategyState.ENTRY_SUBMITTED
    assert len(strat._entry_orders) == 2
    assert "CALL" in strat._entry_orders
    assert "PUT" in strat._entry_orders
    assert strat._entry_fills == {}


def test_arm_waits_for_fresh_quotes_without_recursive_entry_submission():
    strat = create_strategy()
    strat._set_state(StrategyState.QUOTING)
    for quote in strat._quotes.values():
        quote["timestamp"] = time.time() - 60

    strat._handle_command({"command": "ARM"})

    assert strat.state == StrategyState.ARMED
    assert strat._entry_orders == {}

    for quote in strat._quotes.values():
        quote["timestamp"] = time.time()
    strat._attempt_entry()

    assert strat.state == StrategyState.ENTRY_SUBMITTED
    assert len(strat._entry_orders) == 2
    assert len(strat.submitted_orders) == 2


def test_armed_quote_poll_checks_liquidity_even_when_ticks_are_fresh():
    strat = create_strategy()
    strat._set_state(StrategyState.ARMED)
    strat._quotes[str(strat._put_id)]["is_synthetic"] = True
    alternative_checks = []
    strat._select_executable_alternative = lambda: alternative_checks.append(True) or False

    strat._on_poll_quotes()

    assert alternative_checks == [True]
    assert strat.submitted_orders == []
    assert strat._entry_quote_block_reason() == "PUT has only an indicative mark; waiting for a real order book"


def test_spread_limit_is_reported_as_wait_and_prevents_entry():
    strat = create_strategy(max_spread_pct=0.01)
    strat._quotes[str(strat._call_id)]["ask"] = Decimal("1100")
    strat._quotes[str(strat._put_id)]["ask"] = Decimal("1000")
    strat._set_state(StrategyState.ARMED)
    strat._selection_candidates = []

    strat._evaluate_armed_entry()

    assert strat.state == StrategyState.ARMED
    assert strat.submitted_orders == []
    assert "Combined spread 10.00% exceeds limit 1.00%" == strat._entry_quote_block_reason()


def test_sell_entry_uses_bid_size_not_irrelevant_ask_size():
    strat = create_strategy()
    strat._quotes[str(strat._call_id)]["ask_size"] = Decimal("0")
    strat._quotes[str(strat._put_id)]["ask_size"] = Decimal("0")
    strat._set_state(StrategyState.ARMED)
    strat._selection_candidates = []

    strat._evaluate_armed_entry()

    assert strat.state == StrategyState.ENTRY_SUBMITTED
    assert set(strat._entry_orders) == {"CALL", "PUT"}


def test_quote_tick_freshness_uses_local_receive_timestamp():
    strat = create_strategy()
    received_ns = time.time_ns()
    tick = SimpleNamespace(
        instrument_id=strat._call_id,
        bid_price=Decimal("1000"),
        ask_price=Decimal("1010"),
        bid_size=Decimal("1"),
        ask_size=Decimal("1"),
        ts_event=received_ns - 60_000_000_000,
        ts_init=received_ns,
    )

    strat.on_quote_tick(tick)

    call_quote = strat._quotes[str(strat._call_id)]
    assert call_quote["timestamp"] == pytest.approx(received_ns / 1e9)
    assert strat._quotes_fresh()


def test_quote_poll_failure_is_reported_while_armed(monkeypatch):
    import httpx

    strat = create_strategy()
    strat._set_state(StrategyState.ARMED)
    for quote in strat._quotes.values():
        quote["timestamp"] = time.time() - 60
    waits = []
    strat._emit_entry_wait = waits.append

    def fail_request(*args, **kwargs):
        raise httpx.TimeoutException("ticker request timed out")

    monkeypatch.setattr(httpx, "get", fail_request)

    strat._on_poll_quotes()

    assert waits == ["Quote refresh failed: ticker request timed out"]


def test_armed_strategy_selects_nearest_strike_with_real_two_sided_quotes(monkeypatch):
    import httpx

    strat = create_strategy()
    current = strat._selection
    alternate = SelectionResult(
        expiry=current.expiry,
        strike=Decimal("71000"),
        call_id="BTC-28MAR26-71000-C-USDT.BYBIT",
        put_id="BTC-28MAR26-71000-P-USDT.BYBIT",
        ref_price=current.ref_price,
    )
    strat._selection_candidates = [current, alternate]
    strat._set_state(StrategyState.ARMED)

    class MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "retCode": 0,
                "result": {
                    "list": [
                        {"symbol": "BTC-28MAR26-71000-C-USDT", "bid1Price": "1000", "ask1Price": "1010", "bid1Size": "1", "ask1Size": "1"},
                        {"symbol": "BTC-28MAR26-71000-P-USDT", "bid1Price": "900", "ask1Price": "910", "bid1Size": "1", "ask1Size": "1"},
                    ],
                },
            }

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: MockResponse())

    assert strat._select_executable_alternative() is True
    assert strat._selection.strike == Decimal("71000")
    assert strat.state == StrategyState.ENTRY_SUBMITTED
    assert set(strat._entry_orders) == {"CALL", "PUT"}


def test_armed_strategy_waits_when_no_alternative_has_real_quotes(monkeypatch):
    import httpx

    strat = create_strategy()
    current = strat._selection
    strat._selection_candidates = [
        current,
        SelectionResult(
            expiry=current.expiry,
            strike=Decimal("71000"),
            call_id="BTC-28MAR26-71000-C-USDT.BYBIT",
            put_id="BTC-28MAR26-71000-P-USDT.BYBIT",
            ref_price=current.ref_price,
        ),
    ]
    strat._set_state(StrategyState.ARMED)

    class MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"retCode": 0, "result": {"list": []}}

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: MockResponse())

    assert strat._select_executable_alternative() is False
    assert strat._selection.strike == current.strike
    assert strat.state == StrategyState.ARMED
    assert strat.submitted_orders == []


def test_armed_strategy_stays_armed_when_selector_recovers():
    strat = create_strategy()
    strat._selection = None
    strat._call_id = None
    strat._put_id = None
    strat._quotes.clear()
    strat._set_state(StrategyState.ARMED)
    strat._on_poll_quotes = lambda: None

    expiry = datetime.now(timezone.utc) + timedelta(days=1)
    instruments = [
        SimpleNamespace(
            id=f"BTC-TEST-{kind}-USDT.BYBIT",
            option_kind=kind,
            strike_price=Decimal("70000"),
            expiration_utc=expiry,
            underlying="BTC",
            info={"underlyingPrice": "70000"},
        )
        for kind in ("CALL", "PUT")
    ]

    strat._run_selector(instruments)

    assert strat.state == StrategyState.ARMED
    assert strat._call_id is not None
    assert strat._put_id is not None


def test_fills_transition_to_open_and_calc_premium():
    strat = create_strategy()
    strat._set_state(StrategyState.QUOTING)
    strat._handle_command({"command": "ARM"})

    call_oid = strat._entry_orders["CALL"]
    put_oid = strat._entry_orders["PUT"]

    # Fill call leg
    fill_call = MockEvent(
        client_order_id=call_oid,
        instrument_id=strat._call_id,
        last_qty=Decimal("0.01"),
        last_px=Decimal("1000"),
    )
    strat.on_order_filled(fill_call)
    assert strat.state == StrategyState.ENTRY_SUBMITTED  # Still waiting for put

    # Fill put leg
    fill_put = MockEvent(
        client_order_id=put_oid,
        instrument_id=strat._put_id,
        last_qty=Decimal("0.01"),
        last_px=Decimal("900"),
    )
    strat.on_order_filled(fill_put)

    assert strat.state == StrategyState.OPEN
    # Premium = 0.01 * 1000 + 0.01 * 900 = 10 + 9 = 19
    assert strat._entry_premium == Decimal("19.00")


def test_partial_entry_fills_are_accumulated_before_open():
    strat = create_strategy()
    strat._set_state(StrategyState.QUOTING)
    strat._handle_command({"command": "ARM"})

    call_oid = strat._entry_orders["CALL"]
    put_oid = strat._entry_orders["PUT"]
    for price in ("1000", "1100"):
        strat.on_order_filled(MockEvent(
            client_order_id=call_oid,
            instrument_id=strat._call_id,
            last_qty=Decimal("0.005"),
            last_px=Decimal(price),
        ))
    assert strat.state == StrategyState.ENTRY_SUBMITTED
    assert strat._entry_fills["CALL"]["qty"] == Decimal("0.010")
    assert strat._entry_fills["CALL"]["price"] == Decimal("1050")

    strat.on_order_filled(MockEvent(
        client_order_id=put_oid,
        instrument_id=strat._put_id,
        last_qty=Decimal("0.01"),
        last_px=Decimal("900"),
    ))
    assert strat.state == StrategyState.OPEN
    assert strat._entry_premium == Decimal("19.50")


def test_canceled_testnet_orders_are_not_recorded_as_fills():
    strat = create_strategy()
    strat._set_state(StrategyState.QUOTING)
    strat._handle_command({"command": "ARM"})

    strat.on_order_canceled(MockEvent(client_order_id=strat._entry_orders["CALL"]))
    strat.on_order_canceled(MockEvent(client_order_id=strat._entry_orders["PUT"]))

    assert strat.state == StrategyState.QUOTING
    assert strat._entry_fills == {}


def test_completed_pnl_uses_confirmed_exit_fills():
    strat = create_strategy()
    strat._set_state(StrategyState.QUOTING)
    strat._handle_command({"command": "ARM"})
    call_oid = strat._entry_orders["CALL"]
    put_oid = strat._entry_orders["PUT"]

    strat.on_order_filled(MockEvent(
        client_order_id=call_oid,
        instrument_id=strat._call_id,
        last_qty=Decimal("0.01"),
        last_px=Decimal("1000"),
    ))
    strat.on_order_filled(MockEvent(
        client_order_id=put_oid,
        instrument_id=strat._put_id,
        last_qty=Decimal("0.01"),
        last_px=Decimal("900"),
    ))
    strat._mock_positions[str(strat._call_id)] = MockPosition(strat._call_id, Decimal("0.01"))
    strat._mock_positions[str(strat._put_id)] = MockPosition(strat._put_id, Decimal("0.01"))

    strat._request_exit("manual:test")
    call_exit = strat._exit_orders["CALL"]
    put_exit = strat._exit_orders["PUT"]
    strat._mock_positions.pop(str(strat._call_id))
    strat.on_order_filled(MockEvent(
        client_order_id=call_exit,
        instrument_id=strat._call_id,
        last_qty=Decimal("0.01"),
        last_px=Decimal("800"),
    ))
    strat._mock_positions.pop(str(strat._put_id))
    strat.on_order_filled(MockEvent(
        client_order_id=put_exit,
        instrument_id=strat._put_id,
        last_qty=Decimal("0.01"),
        last_px=Decimal("1000"),
    ))

    assert strat.state == StrategyState.CLOSED
    assert Decimal(strat._last_completed_trade["realized_pnl"]) == Decimal("1.00")
    assert Decimal(strat._last_completed_trade["exit_cost"]) == Decimal("18.00")


def test_flatten_command_from_open():
    strat = create_strategy()
    strat._set_state(StrategyState.OPEN)
    strat._entry_premium = Decimal("19.00")

    # Set mock positions
    strat._mock_positions[str(strat._call_id)] = MockPosition(strat._call_id, Decimal("0.01"))
    strat._mock_positions[str(strat._put_id)] = MockPosition(strat._put_id, Decimal("0.01"))

    # Issue FLATTEN
    strat._handle_command({"command": "FLATTEN"})
    assert strat.state == StrategyState.EXITING
    assert len(strat._exit_orders) == 2


def test_flatten_during_entry_waits_for_cancel_before_unwinding_fills():
    strat = create_strategy()
    strat._set_state(StrategyState.QUOTING)
    strat._handle_command({"command": "ARM"})

    call_oid = strat._entry_orders["CALL"]
    put_oid = strat._entry_orders["PUT"]
    canceled = []
    strat.cancel_order = lambda order: canceled.append(order.client_order_id)

    strat.on_order_filled(MockEvent(
        client_order_id=call_oid,
        instrument_id=strat._call_id,
        last_qty=Decimal("0.01"),
        last_px=Decimal("1000"),
    ))
    strat._handle_command({"command": "FLATTEN"})

    assert strat.state == StrategyState.EXITING
    assert canceled == [put_oid]
    assert strat._exit_orders == {}

    # A fill can race the cancel acknowledgement and must also be unwound.
    strat.on_order_filled(MockEvent(
        client_order_id=put_oid,
        instrument_id=strat._put_id,
        last_qty=Decimal("0.005"),
        last_px=Decimal("900"),
    ))
    assert strat._exit_orders == {}

    strat.on_order_canceled(MockEvent(client_order_id=put_oid))
    assert set(strat._exit_orders) == {"CALL", "PUT"}
    assert Decimal(str(strat.submitted_orders[-2].quantity)) == Decimal("0.01")
    assert Decimal(str(strat.submitted_orders[-1].quantity)) == Decimal("0.005")


def test_flatten_during_entry_with_no_fills_closes_after_cancel_acknowledgements():
    strat = create_strategy()
    strat._set_state(StrategyState.QUOTING)
    strat._handle_command({"command": "ARM"})
    call_oid = strat._entry_orders["CALL"]
    put_oid = strat._entry_orders["PUT"]
    strat.cancel_order = lambda order: None

    strat._handle_command({"command": "FLATTEN"})
    assert strat.state == StrategyState.EXITING

    strat.on_order_canceled(MockEvent(client_order_id=call_oid))
    assert strat.state == StrategyState.EXITING
    strat.on_order_canceled(MockEvent(client_order_id=put_oid))

    assert strat.state == StrategyState.CLOSED
    assert strat._exit_orders == {}


def test_exit_completion_to_closed():
    strat = create_strategy()
    strat._set_state(StrategyState.OPEN)
    strat._mock_positions[str(strat._call_id)] = MockPosition(strat._call_id, Decimal("0.01"))
    strat._mock_positions[str(strat._put_id)] = MockPosition(strat._put_id, Decimal("0.01"))

    strat._request_exit("manual:test")
    assert strat.state == StrategyState.EXITING

    # Positions become flat in cache
    strat._mock_positions.pop(str(strat._call_id), None)
    strat._mock_positions.pop(str(strat._put_id), None)

    strat._check_exit_complete()
    assert strat.state == StrategyState.CLOSED


def test_unwind_policy_on_leg_rejection():
    strat = create_strategy()
    strat._set_state(StrategyState.QUOTING)
    strat._handle_command({"command": "ARM"})

    call_oid = strat._entry_orders["CALL"]
    put_oid = strat._entry_orders["PUT"]

    # Call leg fills
    strat.on_order_filled(MockEvent(
        client_order_id=call_oid,
        instrument_id=strat._call_id,
        last_qty=Decimal("0.01"),
        last_px=Decimal("1000"),
    ))

    # Put leg rejected
    strat._mock_positions[str(strat._call_id)] = MockPosition(strat._call_id, Decimal("0.01"))
    strat.on_order_rejected(MockEvent(
        client_order_id=put_oid,
        instrument_id=strat._put_id,
        reason="Insufficient balance",
    ))

    # Strategy should unwind the filled call leg
    assert strat.state == StrategyState.EXITING
    assert "CALL" in strat._exit_orders
