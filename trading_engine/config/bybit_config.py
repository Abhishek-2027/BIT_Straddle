"""Bybit client configuration builder for NautilusTrader."""

from __future__ import annotations

import logging
from nautilus_trader.adapters.bybit.common.enums import BybitProductType
from nautilus_trader.adapters.bybit.config import BybitDataClientConfig, BybitExecClientConfig

from trading_engine.config.settings import settings

logger = logging.getLogger(__name__)


def build_bybit_data_config() -> BybitDataClientConfig:
    """Build the BybitDataClientConfig configured for Testnet Options."""
    is_testnet = settings.BYBIT_TESTNET or settings.BYBIT_ENVIRONMENT.upper() == "TESTNET"

    logger.info(
        "Configuring Bybit Data Client: testnet=%s, product_types=[OPTION]",
        is_testnet,
    )

    return BybitDataClientConfig(
        api_key=settings.effective_api_key or None,
        api_secret=settings.effective_api_secret or None,
        product_types=[BybitProductType.OPTION],
        testnet=is_testnet,
        recv_window_ms=5000,
        update_instruments_interval_mins=60,
        bars_timestamp_on_close=True,
    )


def build_bybit_exec_config() -> BybitExecClientConfig:
    """Build the BybitExecClientConfig configured for Testnet Options."""
    is_testnet = settings.BYBIT_TESTNET or settings.BYBIT_ENVIRONMENT.upper() == "TESTNET"

    logger.info(
        "Configuring Bybit Execution Client: testnet=%s, product_types=[OPTION]",
        is_testnet,
    )

    return BybitExecClientConfig(
        api_key=settings.effective_api_key or None,
        api_secret=settings.effective_api_secret or None,
        product_types=[BybitProductType.OPTION],
        testnet=is_testnet,
        recv_window_ms=5000,
        use_ws_execution_fast=False,
        use_ws_trade_api=False,
    )
