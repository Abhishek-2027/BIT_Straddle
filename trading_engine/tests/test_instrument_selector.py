"""Unit tests for InstrumentSelector and OptionChain."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest

from nautilus_trader.model.enums import OptionKind
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import CryptoOption
from nautilus_trader.model.objects import Price, Quantity, Currency

from trading_engine.instruments.instrument_selector import InstrumentSelector
from trading_engine.instruments.option_chain import OptionContract, OptionPair


def create_mock_option(
    symbol_str: str,
    underlying: str,
    kind: OptionKind,
    strike: str,
    expiry: datetime,
    settlement: str = "USDT",
    multiplier: str = "1.0",
) -> CryptoOption:
    """Helper to instantiate a real NautilusTrader CryptoOption."""
    sym = Symbol(symbol_str)
    inst_id = InstrumentId.from_str(f"{symbol_str}.BYBIT")
    expiry = expiry.replace(microsecond=0)

    return CryptoOption(
        instrument_id=inst_id,
        raw_symbol=sym,
        underlying=Currency.from_str(underlying),
        quote_currency=Currency.from_str(settlement),
        settlement_currency=Currency.from_str(settlement),
        is_inverse=False,
        option_kind=kind,
        strike_price=Price.from_str(strike),
        activation_ns=0,
        expiration_ns=int(expiry.timestamp() * 1_000_000_000),
        price_precision=2,
        size_precision=2,
        price_increment=Price.from_str("0.50"),
        size_increment=Quantity.from_str("0.01"),
        ts_event=0,
        ts_init=0,
        multiplier=Quantity.from_str(multiplier),
        lot_size=Quantity.from_str("0.01"),
        min_quantity=Quantity.from_str("0.01"),
        max_quantity=Quantity.from_str("1000"),
        min_price=Price.from_str("0.1"),
        max_price=Price.from_str("1000000"),
    )


def test_atm_selection_exact_example():
    """Test the exact ATM example from Section 5.4: ref=91250 -> 91000."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=7)

    strikes = ["89000", "90000", "91000", "92000", "93000"]
    options = []
    for s in strikes:
        options.append(create_mock_option(f"BTC-{s}-C", "BTC", OptionKind.CALL, s, exp))
        options.append(create_mock_option(f"BTC-{s}-P", "BTC", OptionKind.PUT, s, exp))

    selector = InstrumentSelector(target_underlying="BTC")
    ref_prices = {exp: Decimal("91250")}

    result = selector.select_atm_straddle(options, ref_prices, current_time=now)

    assert result.is_valid
    assert result.pair.strike == Decimal("91000")
    assert result.ref_price == Decimal("91250")
    assert result.pair.call_contract.strike_price == Decimal("91000")
    assert result.pair.put_contract.strike_price == Decimal("91000")


def test_tie_break_lower_strike():
    """Equidistant strikes (90000 and 92000 with ref 91000) should break to lower (90000)."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=5)

    options = [
        create_mock_option("BTC-90000-C", "BTC", OptionKind.CALL, "90000", exp),
        create_mock_option("BTC-90000-P", "BTC", OptionKind.PUT, "90000", exp),
        create_mock_option("BTC-92000-C", "BTC", OptionKind.CALL, "92000", exp),
        create_mock_option("BTC-92000-P", "BTC", OptionKind.PUT, "92000", exp),
    ]

    selector = InstrumentSelector()
    ref_prices = {exp: Decimal("91000")}

    result = selector.select_atm_straddle(options, ref_prices, current_time=now)
    assert result.is_valid
    assert result.pair.strike == Decimal("90000")


def test_skip_expired_and_non_btc():
    """Expired options and ETH options must be skipped."""
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=1)
    future = now + timedelta(days=3)

    options = [
        # Expired
        create_mock_option("BTC-80000-C-EXP", "BTC", OptionKind.CALL, "80000", past),
        create_mock_option("BTC-80000-P-EXP", "BTC", OptionKind.PUT, "80000", past),
        # ETH
        create_mock_option("ETH-3000-C", "ETH", OptionKind.CALL, "3000", future),
        create_mock_option("ETH-3000-P", "ETH", OptionKind.PUT, "3000", future),
        # Valid BTC
        create_mock_option("BTC-95000-C", "BTC", OptionKind.CALL, "95000", future),
        create_mock_option("BTC-95000-P", "BTC", OptionKind.PUT, "95000", future),
    ]

    selector = InstrumentSelector()
    ref_prices = {future: Decimal("95100")}

    result = selector.select_atm_straddle(options, ref_prices, current_time=now)
    assert result.is_valid
    assert result.pair.strike == Decimal("95000")
    assert result.pair.expiry.date() == future.date()


def test_skip_unpaired_strike():
    """Strikes with only Call or only Put cannot form a straddle."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=2)

    options = [
        # 90000 only has Call
        create_mock_option("BTC-90000-C", "BTC", OptionKind.CALL, "90000", exp),
        # 92000 has both Call and Put
        create_mock_option("BTC-92000-C", "BTC", OptionKind.CALL, "92000", exp),
        create_mock_option("BTC-92000-P", "BTC", OptionKind.PUT, "92000", exp),
    ]

    selector = InstrumentSelector()
    ref_prices = {exp: Decimal("90100")}  # Closer to 90000, but 90000 lacks Put!

    result = selector.select_atm_straddle(options, ref_prices, current_time=now)
    assert result.is_valid
    assert result.pair.strike == Decimal("92000")  # Selected because it has both legs
