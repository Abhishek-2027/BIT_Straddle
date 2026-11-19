"""ATM straddle selector — pure logic, no Nautilus imports."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

try:
    from backend.models import OptionLeg, SelectionResult
except ImportError:
    from models import OptionLeg, SelectionResult


def select_atm_straddle(
    options: list[OptionLeg],
    ref_prices: dict[str, Decimal],
    current_time: datetime,
) -> SelectionResult:
    """Pick the nearest-expiry ATM straddle for BTC.

    Algorithm
    ---------
    1. Keep only BTC, tradable, unexpired options.
    2. Group by expiry. Keep expiries that have at least one strike with
       *both* a CALL and a PUT.
    3. Pick the nearest future expiry.
    4. Within that expiry, choose ``argmin |ref_price - strike|``.
       Tie-break: lower strike.
    5. Return a :class:`SelectionResult` (with ``reason`` on failure).
    """

    candidates = rank_atm_straddles(options, ref_prices, current_time)
    if candidates:
        return candidates[0]
    if not options:
        return SelectionResult(reason="no options provided")

    filtered = [
        o for o in options
        if o.underlying == "BTC"
        and o.tradable
        and o.expiry > current_time
    ]
    if not filtered:
        return SelectionResult(reason="no valid BTC options after filtering")

    kinds_by_strike: dict[tuple[datetime, Decimal], set[str]] = defaultdict(set)
    for option in filtered:
        kinds_by_strike[(option.expiry, option.strike)].add(option.kind)
    if not any({"CALL", "PUT"}.issubset(kinds) for kinds in kinds_by_strike.values()):
        return SelectionResult(reason="no expiry has both a call and a put at the same strike")
    return SelectionResult(reason="no ref_price available for any valid expiry")


def rank_atm_straddles(
    options: list[OptionLeg],
    ref_prices: dict[str, Decimal],
    current_time: datetime,
) -> list[SelectionResult]:
    """Return paired strikes in ATM order for the nearest expiry with a reference price."""
    if not options:
        return []

    # Step 1 — filter
    filtered = [
        o for o in options
        if o.underlying == "BTC"
        and o.tradable
        and o.expiry > current_time
    ]

    if not filtered:
        return []

    # Step 2 — group by expiry, keep only those with paired strikes
    by_expiry: dict[datetime, dict[Decimal, dict[str, OptionLeg]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for o in filtered:
        by_expiry[o.expiry][o.strike][o.kind] = o

    valid_expiries: dict[datetime, dict[Decimal, dict[str, OptionLeg]]] = {}
    for exp, strikes in by_expiry.items():
        paired = {
            s: kinds
            for s, kinds in strikes.items()
            if "CALL" in kinds and "PUT" in kinds
        }
        if paired:
            valid_expiries[exp] = paired

    if not valid_expiries:
        return []

    # Step 3 — nearest future expiry
    nearest_expiry = min(valid_expiries.keys())

    # We need a ref_price for this expiry
    # ref_prices is keyed by expiry ISO string
    expiry_key = nearest_expiry.isoformat()
    ref_price = ref_prices.get(expiry_key)
    if ref_price is None:
        # Try remaining expiries in order
        for exp in sorted(valid_expiries.keys()):
            rp = ref_prices.get(exp.isoformat())
            if rp is not None:
                nearest_expiry = exp
                ref_price = rp
                break

    if ref_price is None:
        # Check for fallback "default" key or any available reference price
        if "default" in ref_prices:
            ref_price = ref_prices["default"]
        elif ref_prices:
            ref_price = next(iter(ref_prices.values()))

    if ref_price is None:
        return []

    # Step 4 — rank paired strikes by distance to spot (lower strike wins ties).
    strikes_map = valid_expiries[nearest_expiry]
    return [
        SelectionResult(
            expiry=nearest_expiry,
            strike=strike,
            call_id=strikes_map[strike]["CALL"].instrument_id,
            put_id=strikes_map[strike]["PUT"].instrument_id,
            ref_price=ref_price,
            reason=None,
        )
        for strike in sorted(strikes_map, key=lambda s: (abs(ref_price - s), s))
    ]
