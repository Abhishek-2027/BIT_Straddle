"""Option chain data structures and pairing models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from nautilus_trader.model.enums import OptionKind
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CryptoOption


@dataclass(frozen=True)
class OptionContract:
    """Normalized representation of a single crypto option contract."""

    instrument_id: InstrumentId
    symbol: str
    underlying: str
    kind: OptionKind
    strike_price: Decimal
    expiration_utc: datetime
    settlement_currency: str
    multiplier: Decimal
    min_quantity: Decimal
    lot_size: Decimal
    raw_instrument: CryptoOption

    @classmethod
    def from_crypto_option(cls, option: CryptoOption) -> OptionContract:
        """Create an OptionContract from a NautilusTrader CryptoOption."""
        underlying_str = str(option.underlying)
        settlement_str = str(option.settlement_currency)

        exp = option.expiration_utc
        if hasattr(exp, "to_pydatetime"):
            exp = exp.to_pydatetime()

        return cls(
            instrument_id=option.id,
            symbol=str(option.symbol),
            underlying=underlying_str,
            kind=option.option_kind,
            strike_price=Decimal(str(option.strike_price)),
            expiration_utc=exp,
            settlement_currency=settlement_str,
            multiplier=Decimal(str(option.multiplier)),
            min_quantity=Decimal(str(option.min_quantity)),
            lot_size=Decimal(str(option.lot_size)),
            raw_instrument=option,
        )


@dataclass(frozen=True)
class OptionPair:
    """A matched Call and Put option pair with identical strike and expiry."""

    expiry: datetime
    strike: Decimal
    call_contract: OptionContract
    put_contract: OptionContract

    @property
    def call_id(self) -> InstrumentId:
        return self.call_contract.instrument_id

    @property
    def put_id(self) -> InstrumentId:
        return self.put_contract.instrument_id


@dataclass
class StraddleSelection:
    """The outcome of the ATM straddle selection algorithm."""

    pair: Optional[OptionPair]
    ref_price: Decimal
    available_expiries: list[datetime]
    available_strikes: list[Decimal]
    reason: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.pair is not None and self.reason is None
