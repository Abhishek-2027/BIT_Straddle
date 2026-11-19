"""BTC ATM Option Instrument Selector for NautilusTrader."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from nautilus_trader.model.enums import OptionKind
from nautilus_trader.model.instruments import CryptoOption

from trading_engine.instruments.option_chain import (
    OptionContract,
    OptionPair,
    StraddleSelection,
)

logger = logging.getLogger(__name__)


class InstrumentSelector:
    """Discovers, filters, and pairs BTC option contracts to select the ATM straddle."""

    def __init__(self, target_underlying: str = "BTC") -> None:
        self.target_underlying = target_underlying.upper()

    def select_atm_straddle(
        self,
        instruments: Sequence[CryptoOption],
        ref_prices: dict[datetime, Decimal],
        current_time: datetime | None = None,
    ) -> StraddleSelection:
        """Execute the complete discovery, filtering, pairing, and ATM selection workflow."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        elif current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        # 1. Filter eligible contracts
        contracts: list[OptionContract] = []
        for inst in instruments:
            if not isinstance(inst, CryptoOption):
                continue

            contract = OptionContract.from_crypto_option(inst)

            # Underlying check
            if self.target_underlying not in contract.underlying.upper():
                continue

            # Expiration check
            exp = contract.expiration_utc
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)

            if exp <= current_time:
                continue

            # Multiplier and quantity validation
            if contract.multiplier <= 0 or contract.min_quantity <= 0:
                continue

            contracts.append(contract)

        if not contracts:
            logger.warning("No eligible active BTC option contracts found.")
            return StraddleSelection(
                pair=None,
                ref_price=Decimal("0"),
                available_expiries=[],
                available_strikes=[],
                reason="No active unexpired BTC option contracts found",
            )

        # 2. Group by (expiry, strike, kind)
        expiry_groups: dict[datetime, dict[Decimal, dict[OptionKind, OptionContract]]] = (
            defaultdict(lambda: defaultdict(dict))
        )
        for c in contracts:
            expiry_groups[c.expiration_utc][c.strike_price][c.kind] = c

        # 3. Filter expiries that have at least one complete Call & Put pair
        valid_expiries: dict[datetime, list[OptionPair]] = {}
        for exp, strikes in expiry_groups.items():
            pairs_for_exp: list[OptionPair] = []
            for strike, kinds in strikes.items():
                if OptionKind.CALL in kinds and OptionKind.PUT in kinds:
                    pairs_for_exp.append(
                        OptionPair(
                            expiry=exp,
                            strike=strike,
                            call_contract=kinds[OptionKind.CALL],
                            put_contract=kinds[OptionKind.PUT],
                        )
                    )
            if pairs_for_exp:
                valid_expiries[exp] = pairs_for_exp

        if not valid_expiries:
            logger.warning("No expiry has a matching Call and Put pair at the same strike.")
            return StraddleSelection(
                pair=None,
                ref_price=Decimal("0"),
                available_expiries=[],
                available_strikes=[],
                reason="No expiry has complete Call/Put pairs",
            )

        sorted_expiries = sorted(valid_expiries.keys())

        # 4. Select the nearest future expiry that has a reference price
        selected_expiry: datetime | None = None
        selected_ref_price: Decimal | None = None

        for exp in sorted_expiries:
            # Check ref price exact match or nearest expiry date match
            rp = ref_prices.get(exp)
            if rp is None:
                # Look for matching timestamp date
                for r_dt, r_val in ref_prices.items():
                    if r_dt.date() == exp.date():
                        rp = r_val
                        break

            if rp is not None and rp > 0:
                selected_expiry = exp
                selected_ref_price = rp
                break

        # Fallback if specific expiry ref_price missing: use any available BTC ref_price
        if selected_ref_price is None and ref_prices:
            selected_expiry = sorted_expiries[0]
            selected_ref_price = next(iter(ref_prices.values()))

        if selected_expiry is None or selected_ref_price is None or selected_ref_price <= 0:
            logger.warning("No valid BTC reference price available to determine ATM strike.")
            return StraddleSelection(
                pair=None,
                ref_price=Decimal("0"),
                available_expiries=sorted_expiries,
                available_strikes=[],
                reason="Missing valid underlying reference price for nearest expiry",
            )

        pairs_in_expiry = valid_expiries[selected_expiry]
        available_strikes = sorted([p.strike for p in pairs_in_expiry])

        # 5. ATM Selection: argmin |strike - ref_price|
        # Deterministic tie-break: pick lower strike
        selected_pair = min(
            pairs_in_expiry,
            key=lambda p: (abs(p.strike - selected_ref_price), p.strike),
        )

        logger.info(
            "Selected ATM Straddle: Expiry=%s, Strike=%s (ref=%s). Call=%s, Put=%s",
            selected_expiry.strftime("%Y-%m-%d %H:%M:%S UTC"),
            selected_pair.strike,
            selected_ref_price,
            selected_pair.call_id,
            selected_pair.put_id,
        )

        return StraddleSelection(
            pair=selected_pair,
            ref_price=selected_ref_price,
            available_expiries=sorted_expiries,
            available_strikes=available_strikes,
        )
