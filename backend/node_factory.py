"""Factory for building and configuring the NautilusTrader Bybit options node."""

from __future__ import annotations

import logging
import signal
import threading
from typing import Optional

# Monkeypatch signal.signal so that NautilusKernel's signal registration on worker threads
# does not trigger "ValueError: signal only works in main thread of the main interpreter" on Linux.
_orig_signal = signal.signal


def _safe_signal(sig, handler):
    if threading.current_thread() is not threading.main_thread():
        return None
    try:
        return _orig_signal(sig, handler)
    except ValueError:
        return None


signal.signal = _safe_signal

# Monkeypatch NautilusKernel._setup_loop so uvloop's Loop.add_signal_handler()
# does not raise "ValueError: add_signal_handler() can only be called from the main thread"
# when TradingNode is run inside a background thread.
try:
    from nautilus_trader.system.kernel import NautilusKernel

    _orig_setup_loop = NautilusKernel._setup_loop

    def _safe_setup_loop(self) -> None:
        try:
            _orig_setup_loop(self)
        except Exception:
            pass

    NautilusKernel._setup_loop = _safe_setup_loop
except Exception:
    pass

try:
    from backend.config import settings
    from backend.strategy import StraddleStrategy, StraddleConfig
    from backend.bybit_compat import install_bybit_order_decoder_compatibility
except ImportError:
    from config import settings
    from strategy import StraddleStrategy, StraddleConfig
    from bybit_compat import install_bybit_order_decoder_compatibility

logger = logging.getLogger("btc_straddle.node_factory")


def build_trading_node():
    """
    Construct and configure the NautilusTrader TradingNode for the selected Bybit environment.
    Targeted at nautilus_trader >= 1.207.0.
    """
    # 1. TradingNode import with version fallback
    try:
        from nautilus_trader.live.node import TradingNode
    except ImportError:
        try:
            from nautilus_trader.live.node import LiveNode as TradingNode  # type: ignore[no-redef]
        except ImportError as e:
            logger.warning("NautilusTrader LiveNode/TradingNode not importable: %s", e)
            return None

    # 2. Node Config imports
    try:
        from nautilus_trader.config import (
            TradingNodeConfig,
            LiveDataEngineConfig,
            LiveExecEngineConfig,
            InstrumentProviderConfig,
        )
    except ImportError:
        try:
            from nautilus_trader.config import (
                LiveNodeConfig as TradingNodeConfig,  # type: ignore[no-redef]
                LiveDataEngineConfig,
                LiveExecEngineConfig,
            )
        except ImportError as e:
            logger.warning("NautilusTrader NodeConfig not importable: %s", e)
            return None

    # 3. Bybit adapter imports
    try:
        from nautilus_trader.adapters.bybit.config import (
            BybitDataClientConfig,
            BybitExecClientConfig,
        )
        from nautilus_trader.adapters.bybit.factories import (
            BybitLiveDataClientFactory,
            BybitLiveExecClientFactory,
        )
        from nautilus_trader.adapters.bybit.common.enums import (
            BybitProductType,
        )
    except ImportError as e:
        logger.warning("NautilusTrader Bybit adapter not importable: %s", e)
        return None

    install_bybit_order_decoder_compatibility()

    is_testnet = settings.bybit_is_testnet
    is_demo = settings.bybit_is_demo
    if is_demo:
        logger.info("Configured for Bybit DEMO Trading.")
    elif is_testnet:
        logger.info("Configured for Bybit TESTNET.")
    else:
        logger.warning("Configured for Bybit MAINNET! Live trading with real funds will occur if armed.")

    if not settings.BYBIT_TESTNET_API_KEY or not settings.BYBIT_TESTNET_API_SECRET:
        logger.error("Bybit %s credentials are not configured; trading node will not start", settings.BYBIT_ENVIRONMENT)
        return None

    # Demo public market data comes from the regular public stream, while
    # authenticated execution uses the isolated Demo API and private stream.
    data_client_config = BybitDataClientConfig(
        api_key=None if is_demo else settings.BYBIT_TESTNET_API_KEY,
        api_secret=None if is_demo else settings.BYBIT_TESTNET_API_SECRET,
        demo=False,
        testnet=is_testnet,
        product_types=[BybitProductType.OPTION],
        instrument_provider=InstrumentProviderConfig(load_all=True),
    )

    # Bybit Exec Client Configuration
    exec_client_config = BybitExecClientConfig(
        api_key=settings.BYBIT_TESTNET_API_KEY,
        api_secret=settings.BYBIT_TESTNET_API_SECRET,
        demo=is_demo,
        testnet=is_testnet,
        base_url_ws_private=(
            "wss://stream-demo.bybit.com/v5/private" if is_demo else None
        ),
        use_ws_trade_api=False,
        product_types=[BybitProductType.OPTION],
        instrument_provider=InstrumentProviderConfig(load_all=True),
    )

    # Trading Node Configuration
    node_config = TradingNodeConfig(
        trader_id="BTC-STRADDLE-TRADER",
        data_engine=LiveDataEngineConfig(),
        exec_engine=LiveExecEngineConfig(),
        data_clients={"BYBIT": data_client_config},
        exec_clients={"BYBIT": exec_client_config},
    )

    node = TradingNode(config=node_config)
    node.add_data_client_factory("BYBIT", BybitLiveDataClientFactory)
    node.add_exec_client_factory("BYBIT", BybitLiveExecClientFactory)

    # Strategy configuration
    straddle_config = StraddleConfig(
        sl_pct=settings.SL_PCT,
        tp_pct=settings.TP_PCT,
        qty=settings.QTY,
        max_spread_pct=settings.MAX_SPREAD_PCT,
        stale_quote_secs=settings.STALE_QUOTE_SECS,
        exit_watchdog_secs=settings.EXIT_WATCHDOG_SECS,
        auto_enter=settings.AUTO_ENTER,
        entry_order_style=settings.ENTRY_ORDER_STYLE,
        exit_order_style=settings.EXIT_ORDER_STYLE,
        leg_fail_policy=settings.LEG_FAIL_POLICY,
    )

    strategy = StraddleStrategy(config=straddle_config)
    node.trader.add_strategy(strategy)

    return node
