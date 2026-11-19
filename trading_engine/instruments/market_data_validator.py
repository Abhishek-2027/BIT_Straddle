"""Validation rules for incoming real-time option market data (QuoteTick)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import InstrumentId

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidatedQuote:
    """Represents a sanitized, validated BBO quote for an option instrument."""

    instrument_id: InstrumentId
    bid_price: Decimal
    ask_price: Decimal
    bid_size: Decimal
    ask_size: Decimal
    spread: Decimal
    spread_pct: Decimal
    timestamp_utc: datetime
    is_valid: bool
    rejection_reason: Optional[str] = None


class MarketDataValidator:
    """Validates top-of-book option quotes against exchange anomalies."""

    def __init__(self, max_stale_secs: int = 5, max_spread_pct: float = 0.05) -> None:
        self.max_stale_secs = max_stale_secs
        self.max_spread_pct = Decimal(str(max_spread_pct))

    def validate_quote(
        self,
        tick: QuoteTick,
        current_time_utc: datetime | None = None,
    ) -> ValidatedQuote:
        """Validate QuoteTick according to section 5.5 rules:

        - Reject missing quotes
        - Reject zero prices
        - Reject non-positive quantities
        - Reject crossed or locked markets (bid >= ask)
        - Reject stale quotes (age > max_stale_secs)
        """
        if current_time_utc is None:
            current_time_utc = datetime.now(timezone.utc)
        elif current_time_utc.tzinfo is None:
            current_time_utc = current_time_utc.replace(tzinfo=timezone.utc)

        bid = Decimal(str(tick.bid_price))
        ask = Decimal(str(tick.ask_price))
        bid_size = Decimal(str(tick.bid_size))
        ask_size = Decimal(str(tick.ask_size))

        # Timestamp conversion from nanoseconds
        tick_ts = datetime.fromtimestamp(tick.ts_event / 1e9, tz=timezone.utc)

        # 1. Zero or negative price check
        if bid <= Decimal("0") or ask <= Decimal("0"):
            return ValidatedQuote(
                instrument_id=tick.instrument_id,
                bid_price=bid,
                ask_price=ask,
                bid_size=bid_size,
                ask_size=ask_size,
                spread=Decimal("0"),
                spread_pct=Decimal("0"),
                timestamp_utc=tick_ts,
                is_valid=False,
                rejection_reason=f"Non-positive quote prices (bid={bid}, ask={ask})",
            )

        # 2. Invalid / zero quantities
        if bid_size <= Decimal("0") or ask_size <= Decimal("0"):
            return ValidatedQuote(
                instrument_id=tick.instrument_id,
                bid_price=bid,
                ask_price=ask,
                bid_size=bid_size,
                ask_size=ask_size,
                spread=Decimal("0"),
                spread_pct=Decimal("0"),
                timestamp_utc=tick_ts,
                is_valid=False,
                rejection_reason=f"Non-positive quote sizes (bid_sz={bid_size}, ask_sz={ask_size})",
            )

        # 3. Crossed or locked market
        if bid >= ask:
            return ValidatedQuote(
                instrument_id=tick.instrument_id,
                bid_price=bid,
                ask_price=ask,
                bid_size=bid_size,
                ask_size=ask_size,
                spread=ask - bid,
                spread_pct=Decimal("0"),
                timestamp_utc=tick_ts,
                is_valid=False,
                rejection_reason=f"Crossed/locked market (bid={bid} >= ask={ask})",
            )

        # 4. Stale quote check
        age_secs = (current_time_utc - tick_ts).total_seconds()
        if age_secs > self.max_stale_secs:
            return ValidatedQuote(
                instrument_id=tick.instrument_id,
                bid_price=bid,
                ask_price=ask,
                bid_size=bid_size,
                ask_size=ask_size,
                spread=ask - bid,
                spread_pct=(ask - bid) / bid,
                timestamp_utc=tick_ts,
                is_valid=False,
                rejection_reason=f"Quote is stale ({age_secs:.1f}s > {self.max_stale_secs}s limit)",
            )

        spread = ask - bid
        spread_pct = spread / bid

        return ValidatedQuote(
            instrument_id=tick.instrument_id,
            bid_price=bid,
            ask_price=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            spread=spread,
            spread_pct=spread_pct,
            timestamp_utc=tick_ts,
            is_valid=True,
            rejection_reason=None,
        )
