"""Unit tests for MarketDataValidator."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal

from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from trading_engine.instruments.market_data_validator import MarketDataValidator


def make_tick(bid: str, ask: str, bid_sz: str, ask_sz: str, ts_utc: datetime) -> QuoteTick:
    inst_id = InstrumentId.from_str("BTC-27MAR26-90000-C-USDT-OPTION.BYBIT")
    return QuoteTick(
        instrument_id=inst_id,
        bid_price=Price.from_str(bid),
        ask_price=Price.from_str(ask),
        bid_size=Quantity.from_str(bid_sz),
        ask_size=Quantity.from_str(ask_sz),
        ts_event=int(ts_utc.timestamp() * 1_000_000_000),
        ts_init=int(ts_utc.timestamp() * 1_000_000_000),
    )


def test_valid_quote():
    now = datetime.now(timezone.utc)
    tick = make_tick("1000", "1020", "2.5", "3.0", now)
    validator = MarketDataValidator(max_stale_secs=5)

    res = validator.validate_quote(tick, current_time_utc=now)
    assert res.is_valid
    assert res.spread == Decimal("20")
    assert res.spread_pct == Decimal("20") / Decimal("1000")


def test_crossed_market_rejected():
    now = datetime.now(timezone.utc)
    tick = make_tick("1050", "1020", "1.0", "1.0", now)
    validator = MarketDataValidator()

    res = validator.validate_quote(tick, current_time_utc=now)
    assert not res.is_valid
    assert "Crossed/locked" in res.rejection_reason


def test_zero_price_rejected():
    now = datetime.now(timezone.utc)
    tick = make_tick("0", "1020", "1.0", "1.0", now)
    validator = MarketDataValidator()

    res = validator.validate_quote(tick, current_time_utc=now)
    assert not res.is_valid
    assert "Non-positive quote prices" in res.rejection_reason


def test_stale_quote_rejected():
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(seconds=10)
    tick = make_tick("1000", "1020", "1.0", "1.0", old_time)
    validator = MarketDataValidator(max_stale_secs=5)

    res = validator.validate_quote(tick, current_time_utc=now)
    assert not res.is_valid
    assert "stale" in res.rejection_reason.lower()
