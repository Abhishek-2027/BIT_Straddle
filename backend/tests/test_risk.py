"""Tests for backend.risk — risk calculation logic."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.risk import buyback_cost, decide, entry_premium, spread_pct, thresholds

D = Decimal


# ------------------------------------------------------------------
# entry_premium
# ------------------------------------------------------------------
def test_entry_premium_basic():
    legs = [(D("1"), D("1000"), D("1")), (D("1"), D("900"), D("1"))]
    assert entry_premium(legs) == D("1900")


# ------------------------------------------------------------------
# buyback_cost
# ------------------------------------------------------------------
def test_buyback_cost_basic():
    legs = [(D("1"), D("1000"), D("1")), (D("1"), D("900"), D("1"))]
    asks = [D("960"), D("900")]
    assert buyback_cost(legs, asks) == D("1860")


# ------------------------------------------------------------------
# SL triggers at boundary (cost == sl exactly)
# ------------------------------------------------------------------
def test_sl_triggers_at_boundary():
    entry = D("1900")
    sl, _tp = thresholds(entry, 0.01, 0.02)
    assert sl == D("1919")
    assert decide(sl, entry, 0.01, 0.02) == "STOP_LOSS"


# ------------------------------------------------------------------
# TP triggers at boundary
# ------------------------------------------------------------------
def test_tp_triggers_at_boundary():
    entry = D("1900")
    _sl, tp = thresholds(entry, 0.01, 0.02)
    assert tp == D("1862")
    assert decide(tp, entry, 0.01, 0.02) == "TAKE_PROFIT"


# ------------------------------------------------------------------
# No trigger between thresholds
# ------------------------------------------------------------------
def test_no_trigger_between_thresholds():
    entry = D("1900")
    assert decide(D("1890"), entry, 0.01, 0.02) is None


# ------------------------------------------------------------------
# Multiplier handling (multiplier != 1)
# ------------------------------------------------------------------
def test_multiplier_handling():
    legs = [(D("2"), D("500"), D("0.1")), (D("3"), D("400"), D("0.1"))]
    # 2*500*0.1 + 3*400*0.1 = 100 + 120 = 220
    assert entry_premium(legs) == D("220")


# ------------------------------------------------------------------
# Unequal quantities across legs
# ------------------------------------------------------------------
def test_unequal_quantities():
    legs = [(D("2"), D("1000"), D("1")), (D("3"), D("900"), D("1"))]
    # 2*1000 + 3*900 = 2000 + 2700 = 4700
    assert entry_premium(legs) == D("4700")


# ------------------------------------------------------------------
# spread_pct calculation
# ------------------------------------------------------------------
def test_spread_pct():
    bids = [D("990"), D("890")]
    asks = [D("1010"), D("910")]
    # spreads = 20 + 20 = 40
    # mids = 1000 + 900 = 1900
    result = spread_pct(bids, asks)
    assert pytest.approx(result, rel=1e-9) == 40 / 1900


# ------------------------------------------------------------------
# Worked example from the plan
# ------------------------------------------------------------------
def test_worked_example():
    """Entry 1000+900=1900, sl=1919, tp=1862, asks 960+900=1860 → TAKE_PROFIT."""
    legs = [(D("1"), D("1000"), D("1")), (D("1"), D("900"), D("1"))]
    entry = entry_premium(legs)
    assert entry == D("1900")

    sl, tp = thresholds(entry, 0.01, 0.02)
    assert sl == D("1919")
    assert tp == D("1862")

    asks = [D("960"), D("900")]
    cost = buyback_cost(legs, asks)
    assert cost == D("1860")

    result = decide(cost, entry, 0.01, 0.02)
    assert result == "TAKE_PROFIT"
