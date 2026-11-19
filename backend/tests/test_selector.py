"""Tests for backend.selector — ATM straddle selection logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.models import OptionLeg, SelectionResult
from backend.selector import select_atm_straddle

NOW = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)
NEAR = NOW + timedelta(hours=4)
FAR = NOW + timedelta(hours=24)


def _leg(
    strike: int | float,
    kind: str,
    expiry: datetime = NEAR,
    underlying: str = "BTC",
    tradable: bool = True,
) -> OptionLeg:
    return OptionLeg(
        underlying=underlying,
        kind=kind,
        strike=Decimal(str(strike)),
        expiry=expiry,
        instrument_id=f"{underlying}-{expiry.isoformat()}-{strike}-{kind}",
        tradable=tradable,
    )


# ------------------------------------------------------------------
# 1. Nearest expiry selected
# ------------------------------------------------------------------
def test_nearest_expiry_selected():
    options = [
        _leg(100000, "CALL", NEAR),
        _leg(100000, "PUT", NEAR),
        _leg(100000, "CALL", FAR),
        _leg(100000, "PUT", FAR),
    ]
    ref = {NEAR.isoformat(): Decimal("100000"), FAR.isoformat(): Decimal("100000")}
    result = select_atm_straddle(options, ref, NOW)
    assert result.expiry == NEAR
    assert result.reason is None


# ------------------------------------------------------------------
# 2. Skip expiry missing a leg (call without put)
# ------------------------------------------------------------------
def test_skip_expiry_missing_leg():
    options = [
        _leg(100000, "CALL", NEAR),  # no PUT for NEAR
        _leg(100000, "CALL", FAR),
        _leg(100000, "PUT", FAR),
    ]
    ref = {NEAR.isoformat(): Decimal("100000"), FAR.isoformat(): Decimal("100000")}
    result = select_atm_straddle(options, ref, NOW)
    assert result.expiry == FAR
    assert result.reason is None


# ------------------------------------------------------------------
# 3. ATM nearest strike chosen correctly
# ------------------------------------------------------------------
def test_atm_nearest_strike():
    options = [
        _leg(99000, "CALL"),
        _leg(99000, "PUT"),
        _leg(100000, "CALL"),
        _leg(100000, "PUT"),
        _leg(101000, "CALL"),
        _leg(101000, "PUT"),
    ]
    ref = {NEAR.isoformat(): Decimal("100200")}
    result = select_atm_straddle(options, ref, NOW)
    assert result.strike == Decimal("100000")


# ------------------------------------------------------------------
# 4. Tie-break goes to lower strike
# ------------------------------------------------------------------
def test_tie_break_lower_strike():
    options = [
        _leg(99500, "CALL"),
        _leg(99500, "PUT"),
        _leg(100500, "CALL"),
        _leg(100500, "PUT"),
    ]
    # ref_price = 100000 → equidistant from both strikes
    ref = {NEAR.isoformat(): Decimal("100000")}
    result = select_atm_straddle(options, ref, NOW)
    assert result.strike == Decimal("99500")


# ------------------------------------------------------------------
# 5. Missing ref price skips that expiry
# ------------------------------------------------------------------
def test_missing_ref_price_skips_expiry():
    options = [
        _leg(100000, "CALL", NEAR),
        _leg(100000, "PUT", NEAR),
        _leg(100000, "CALL", FAR),
        _leg(100000, "PUT", FAR),
    ]
    # Only FAR has a ref price
    ref = {FAR.isoformat(): Decimal("100000")}
    result = select_atm_straddle(options, ref, NOW)
    assert result.expiry == FAR
    assert result.reason is None


# ------------------------------------------------------------------
# 6. Mixed underlyings filtered out (ETH ignored)
# ------------------------------------------------------------------
def test_eth_ignored():
    options = [
        _leg(100000, "CALL", NEAR, underlying="ETH"),
        _leg(100000, "PUT", NEAR, underlying="ETH"),
        _leg(100000, "CALL", FAR, underlying="BTC"),
        _leg(100000, "PUT", FAR, underlying="BTC"),
    ]
    ref = {NEAR.isoformat(): Decimal("100000"), FAR.isoformat(): Decimal("100000")}
    result = select_atm_straddle(options, ref, NOW)
    assert result.expiry == FAR  # ETH expiry ignored
    assert "BTC" in result.call_id


# ------------------------------------------------------------------
# 7. All expired options returns failure
# ------------------------------------------------------------------
def test_all_expired():
    past = NOW - timedelta(hours=1)
    options = [
        _leg(100000, "CALL", past),
        _leg(100000, "PUT", past),
    ]
    ref = {past.isoformat(): Decimal("100000")}
    result = select_atm_straddle(options, ref, NOW)
    assert result.reason is not None
    assert result.strike is None


# ------------------------------------------------------------------
# 8. Empty input returns failure
# ------------------------------------------------------------------
def test_empty_input():
    result = select_atm_straddle([], {}, NOW)
    assert result.reason is not None
    assert result.expiry is None
