"""Narrow compatibility handling for Bybit order response schema differences."""

from __future__ import annotations

import json
import logging
from functools import wraps
from typing import Any

logger = logging.getLogger("btc_straddle.bybit_compat")

_OPTIONAL_ORDER_PRICE_FIELDS = ("tpLimitPrice", "slLimitPrice")


def _normalize_smp_group(raw: bytes) -> bytes:
    """Normalize optional Bybit fields which NautilusTrader models as required."""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return raw

    if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
        return raw
    orders = payload["result"].get("list")
    if not isinstance(orders, list):
        return raw
    changed = False
    for order in orders:
        if not isinstance(order, dict):
            continue
        for field in _OPTIONAL_ORDER_PRICE_FIELDS:
            if field not in order:
                order[field] = ""
                changed = True
        value = order.get("smpGroup")
        if isinstance(value, str):
            try:
                order["smpGroup"] = int(value)
                changed = True
            except ValueError:
                continue

    if not changed:
        return raw
    return json.dumps(payload, separators=(",", ":")).encode()


def _normalize_ws_account_order_update(raw: bytes) -> bytes:
    """Fill Bybit's omitted optional TP/SL fields in private order updates."""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return raw

    if not isinstance(payload, dict):
        return raw
    orders = payload.get("data")
    if not isinstance(orders, list):
        return raw

    changed = False
    for order in orders:
        if not isinstance(order, dict):
            continue
        for field in _OPTIONAL_ORDER_PRICE_FIELDS:
            if field not in order:
                order[field] = ""
                changed = True

    if not changed:
        return raw
    return json.dumps(payload, separators=(",", ":")).encode()


class _SmpGroupCompatibleDecoder:
    def __init__(self, decoder: Any) -> None:
        self._decoder = decoder

    def decode(self, raw: bytes) -> Any:
        return self._decoder.decode(_normalize_smp_group(raw))


class _WsAccountOrderCompatibleDecoder:
    def __init__(self, decoder: Any) -> None:
        self._decoder = decoder

    def decode(self, raw: bytes) -> Any:
        return self._decoder.decode(_normalize_ws_account_order_update(raw))


def install_bybit_order_decoder_compatibility() -> None:
    """Normalize Bybit order fields omitted from REST and private WebSocket responses."""
    from nautilus_trader.adapters.bybit.endpoints.trade.open_orders import (
        BybitOpenOrdersEndpoint,
    )
    from nautilus_trader.adapters.bybit.endpoints.trade.order_history import (
        BybitOrderHistoryEndpoint,
    )
    from nautilus_trader.adapters.bybit.execution import BybitExecutionClient

    for endpoint_type in (BybitOpenOrdersEndpoint, BybitOrderHistoryEndpoint):
        original_init = endpoint_type.__init__
        if getattr(original_init, "_btc_straddle_smp_group_compat", False):
            continue

        @wraps(original_init)
        def compatible_init(self, *args, _original_init=original_init, **kwargs):
            _original_init(self, *args, **kwargs)
            self._get_resp_decoder = _SmpGroupCompatibleDecoder(self._get_resp_decoder)

        compatible_init._btc_straddle_smp_group_compat = True
        endpoint_type.__init__ = compatible_init

    original_exec_init = BybitExecutionClient.__init__
    if not getattr(original_exec_init, "_btc_straddle_ws_order_compat", False):
        @wraps(original_exec_init)
        def compatible_exec_init(self, *args, _original_init=original_exec_init, **kwargs):
            _original_init(self, *args, **kwargs)
            self._decoder_ws_account_order_update = _WsAccountOrderCompatibleDecoder(
                self._decoder_ws_account_order_update,
            )

        compatible_exec_init._btc_straddle_ws_order_compat = True
        BybitExecutionClient.__init__ = compatible_exec_init

    logger.info("Enabled Bybit REST and private WebSocket order response compatibility")
