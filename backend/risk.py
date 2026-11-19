"""Risk calculations — pure logic, no Nautilus imports.

All monetary values use :class:`~decimal.Decimal` for precision.
"""

from __future__ import annotations

from decimal import Decimal


def entry_premium(legs: list[tuple[Decimal, Decimal, Decimal]]) -> Decimal:
    """Total premium received when selling the straddle.

    Parameters
    ----------
    legs : list of (qty, avg_fill_price, multiplier)
        One tuple per leg.

    Returns
    -------
    Decimal
        Sum of ``qty * avg_fill_price * multiplier`` across all legs.
    """
    return sum(qty * price * mult for qty, price, mult in legs)


def buyback_cost(
    legs: list[tuple[Decimal, Decimal, Decimal]],
    asks: list[Decimal],
) -> Decimal:
    """Cost to buy back (close) the straddle at current ask prices.

    Parameters
    ----------
    legs : list of (qty, avg_fill_price, multiplier)
        Same shape as *entry_premium*.
    asks : list of Decimal
        Current ask price for each leg (same order as *legs*).

    Returns
    -------
    Decimal
        Sum of ``qty * ask * multiplier`` across all legs.
    """
    return sum(
        qty * ask * mult
        for (qty, _price, mult), ask in zip(legs, asks)
    )


def thresholds(
    entry: Decimal,
    sl_pct: float,
    tp_pct: float,
) -> tuple[Decimal, Decimal]:
    """Compute stop-loss and take-profit cost thresholds.

    Parameters
    ----------
    entry : Decimal
        Total premium received at entry.
    sl_pct : float
        Stop-loss percentage (e.g. 0.01 for 1 %).
    tp_pct : float
        Take-profit percentage (e.g. 0.02 for 2 %).

    Returns
    -------
    (sl_level, tp_level)
        * ``sl_level = entry * (1 + sl_pct)`` — exit if buyback cost reaches
          this or above.
        * ``tp_level = entry * (1 - tp_pct)`` — exit if buyback cost falls to
          this or below.
    """
    sl = entry * (1 + Decimal(str(sl_pct)))
    tp = entry * (1 - Decimal(str(tp_pct)))
    return sl, tp


def decide(
    cost: Decimal,
    entry: Decimal,
    sl_pct: float,
    tp_pct: float,
) -> str | None:
    """Return a risk decision based on current buyback cost.

    Parameters
    ----------
    cost : Decimal
        Current buyback cost.
    entry : Decimal
        Entry premium received.
    sl_pct, tp_pct : float
        Stop-loss / take-profit percentages.

    Returns
    -------
    ``"STOP_LOSS"`` if *cost* ≥ sl threshold, ``"TAKE_PROFIT"`` if
    *cost* ≤ tp threshold, else ``None``.
    """
    sl, tp = thresholds(entry, sl_pct, tp_pct)
    if cost >= sl:
        return "STOP_LOSS"
    if cost <= tp:
        return "TAKE_PROFIT"
    return None


def spread_pct(bids: list[Decimal], asks: list[Decimal]) -> float:
    """Weighted average spread as a fraction of the mid price.

    Parameters
    ----------
    bids, asks : list of Decimal
        Bid and ask prices for each leg (same order).

    Returns
    -------
    float
        ``sum(ask - bid) / sum(mid)`` where ``mid = (bid + ask) / 2``.
    """
    total_spread = sum(a - b for a, b in zip(asks, bids))
    total_mid = sum((a + b) / 2 for a, b in zip(asks, bids))
    if total_mid == 0:
        return 0.0
    return float(total_spread / total_mid)
