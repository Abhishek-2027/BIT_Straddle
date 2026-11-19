from __future__ import annotations

import msgspec
import pytest

from backend.bybit_compat import (
    _SmpGroupCompatibleDecoder,
    _WsAccountOrderCompatibleDecoder,
    _normalize_smp_group,
    _normalize_ws_account_order_update,
)


class _Order(msgspec.Struct):
    smpGroup: int
    tpLimitPrice: str
    slLimitPrice: str


class _Result(msgspec.Struct):
    items: list[_Order] = msgspec.field(name="list")


class _Response(msgspec.Struct):
    result: _Result


class _WsOrder(msgspec.Struct):
    tpLimitPrice: str
    slLimitPrice: str


class _WsResponse(msgspec.Struct):
    data: list[_WsOrder]


def test_numeric_string_smp_group_decodes_without_relaxing_schema():
    decoder = _SmpGroupCompatibleDecoder(msgspec.json.Decoder(_Response))

    result = decoder.decode(b'{"result":{"list":[{"smpGroup":"12"}]}}')

    assert result.result.items[0].smpGroup == 12
    assert result.result.items[0].tpLimitPrice == ""
    assert result.result.items[0].slLimitPrice == ""


def test_normalization_leaves_non_numeric_values_for_strict_decoder_to_reject():
    raw = b'{"result":{"list":[{"smpGroup":"not-a-number"}]}}'
    decoder = _SmpGroupCompatibleDecoder(msgspec.json.Decoder(_Response))

    normalized = _normalize_smp_group(raw)

    assert b'"tpLimitPrice":""' in normalized
    assert b'"slLimitPrice":""' in normalized
    with pytest.raises(msgspec.ValidationError):
        decoder.decode(raw)


def test_missing_optional_prices_are_added_even_when_smp_group_is_already_integer():
    raw = b'{"result":{"list":[{"smpGroup":12}]}}'
    decoder = _SmpGroupCompatibleDecoder(msgspec.json.Decoder(_Response))

    result = decoder.decode(raw)

    assert result.result.items[0].smpGroup == 12
    assert result.result.items[0].tpLimitPrice == ""
    assert result.result.items[0].slLimitPrice == ""


def test_websocket_order_update_fills_missing_optional_prices():
    raw = b'{"topic":"order","data":[{"orderId":"123"}]}'
    decoder = _WsAccountOrderCompatibleDecoder(msgspec.json.Decoder(_WsResponse))

    result = decoder.decode(raw)

    assert result.data[0].tpLimitPrice == ""
    assert result.data[0].slLimitPrice == ""


def test_websocket_normalization_preserves_existing_optional_prices():
    raw = b'{"topic":"order","data":[{"tpLimitPrice":"10","slLimitPrice":"9"}]}'

    normalized = _normalize_ws_account_order_update(raw)

    assert normalized == raw
