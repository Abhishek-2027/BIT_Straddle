"""Trading Engine Main Entry Point: NautilusTrader + Bybit Options."""

from __future__ import annotations

import logging
import signal
import sys
from pathlib import Path

from nautilus_trader.live.node import TradingNode
from nautilus_trader.live.config import TradingNodeConfig
from nautilus_trader.config import LiveDataEngineConfig, LiveExecEngineConfig
from nautilus_trader.adapters.bybit.factories import (
    BybitLiveDataClientFactory,
    BybitLiveExecClientFactory,
)

from trading_engine.config.settings import settings
from trading_engine.config.bybit_config import (
    build_bybit_data_config,
    build_bybit_exec_config,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("trading_engine")


def create_trading_node(trader_id: str = "BTC-STRADDLE-001") -> TradingNode:
    """Build and assemble the NautilusTrader TradingNode with Bybit clients."""
    data_cfg = build_bybit_data_config()
    exec_cfg = build_bybit_exec_config()

    node_cfg = TradingNodeConfig(
        trader_id=trader_id,
        data_engine=LiveDataEngineConfig(),
        exec_engine=LiveExecEngineConfig(),
        data_clients={"BYBIT": data_cfg},
        exec_clients={"BYBIT": exec_cfg},
    )

    node = TradingNode(config=node_cfg)
    node.add_data_client_factory("BYBIT", BybitLiveDataClientFactory)
    node.add_exec_client_factory("BYBIT", BybitLiveExecClientFactory)

    return node


def main() -> None:
    """Initialize and run the TradingNode event loop."""
    logger.info("Initializing NautilusTrader Bybit Options Trading Engine...")

    node = create_trading_node()

    def handle_shutdown(signum, frame):
        logger.info("Shutdown signal received (%s). Stopping trading node...", signum)
        try:
            node.stop()
        except Exception as e:
            logger.warning("Error stopping node: %s", e)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        logger.info("Building TradingNode...")
        node.build()
        logger.info("TradingNode built successfully. Running event loop...")
        node.run()
    except Exception as exc:
        logger.exception("Fatal error in TradingNode: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
