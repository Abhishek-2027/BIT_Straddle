"""Tests for duplicate exit protection in StraddleStrategy."""

from __future__ import annotations

import time
from decimal import Decimal
from datetime import datetime, timezone
import pytest

from backend.models import StrategyState, SelectionResult
from backend.strategy import (
    StraddleStrategy,
    StraddleConfig,
    InstrumentId,
    Position,
)


class MockPosition:
    def __init__(self, instrument_id, quantity):
        self.instrument_id = instrument_id
        self.quantity = quantity


def create_strategy_in_open_state():
    cfg = StraddleConfig(
        sl_pct=0.01,
        tp_pct=0.02,
        qty=0.05,  # Config has 0.05
        max_spread_pct=0.05,
    )
    strat = StraddleStrategy(config=cfg)

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

    # Open state with partial/actual positions in cache = 0.02 (different from cfg 0.05)
    strat._set_state(StrategyState.OPEN)
    strat._entry_premium = Decimal("38.00")
    strat._mock_positions[call_id] = MockPosition(strat._call_id, Decimal("0.02"))
    strat._mock_positions[put_id] = MockPosition(strat._put_id, Decimal("0.02"))
    return strat


def test_duplicate_exit_state_guard():
    strat = create_strategy_in_open_state()

    # First exit request
    strat._request_exit("risk:STOP_LOSS")
    assert strat.state == StrategyState.EXITING
    first_exit_orders = dict(strat._exit_orders)
    assert len(first_exit_orders) == 2

    submitted_count_first = len(strat.submitted_orders)

    # Second exit request while EXITING should be ignored by the state guard
    strat._request_exit("duplicate:FLATTEN")
    assert strat.state == StrategyState.EXITING
    assert len(strat.submitted_orders) == submitted_count_first

    # Third exit request while CLOSED should also be ignored
    strat._set_state(StrategyState.CLOSED)
    strat._request_exit("duplicate:after_close")
    assert len(strat.submitted_orders) == submitted_count_first


def test_exit_uses_cache_quantity_and_reduce_only():
    strat = create_strategy_in_open_state()
    # Cache quantity is 0.02, while cfg.qty is 0.05
    strat._request_exit("risk:STOP_LOSS")

    # Inspect submitted exit orders
    for order in strat.submitted_orders:
        assert order.reduce_only is True
        assert Decimal(str(order.quantity)) == Decimal("0.02")


def test_exit_skips_flat_leg():
    strat = create_strategy_in_open_state()
    # Put leg is already flat in cache
    strat._mock_positions.pop(str(strat._put_id), None)

    strat._request_exit("manual:single_leg")
    # Only CALL exit order should be generated
    assert "CALL" in strat._exit_orders
    assert "PUT" not in strat._exit_orders
