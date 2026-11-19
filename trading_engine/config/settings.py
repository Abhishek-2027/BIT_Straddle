"""Trading engine settings loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import model_validator

# Locate root .env
_CURRENT_DIR = Path(__file__).resolve().parent
_ENGINE_DIR = _CURRENT_DIR.parent
_ROOT_DIR = _ENGINE_DIR.parent

for env_path in (_ROOT_DIR / ".env", _ENGINE_DIR / ".env"):
    if env_path.exists():
        load_dotenv(env_path)


class TradingEngineSettings(BaseSettings):
    """Configuration for NautilusTrader Trading Engine & Bybit Adapter."""

    # Bybit Credentials
    BYBIT_API_KEY: str = ""
    BYBIT_API_SECRET: str = ""
    BYBIT_TESTNET_API_KEY: str = ""
    BYBIT_TESTNET_API_SECRET: str = ""
    BYBIT_TESTNET: bool = True
    BYBIT_ENVIRONMENT: str = "TESTNET"

    # Strategy Sizing & Risk Controls
    QTY: float = 0.01
    SL_PCT: float = 0.01
    TP_PCT: float = 0.02
    MAX_SPREAD_PCT: float = 0.015

    # Timing & Tolerances
    STALE_QUOTE_SECS: int = 5
    EXIT_WATCHDOG_SECS: int = 10

    # Execution Styles
    AUTO_ENTER: bool = False
    ENTRY_ORDER_STYLE: str = "ioc_limit"
    EXIT_ORDER_STYLE: str = "ioc_limit"
    LEG_FAIL_POLICY: str = "unwind"

    # IPC / Backend Communication
    IPC_PORT: int = 8000
    IPC_HOST: str = "127.0.0.1"

    @property
    def effective_api_key(self) -> str:
        return self.BYBIT_TESTNET_API_KEY or self.BYBIT_API_KEY

    @property
    def effective_api_secret(self) -> str:
        return self.BYBIT_TESTNET_API_SECRET or self.BYBIT_API_SECRET

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: dict):
        # Resolve Bybit API Key
        key = (
            os.environ.get("BYBIT_TESTNET_API_KEY")
            or os.environ.get("BYBIT_API_KEY")
            or data.get("BYBIT_TESTNET_API_KEY")
            or data.get("BYBIT_API_KEY")
            or ""
        )
        data["BYBIT_TESTNET_API_KEY"] = key
        data["BYBIT_API_KEY"] = key

        # Resolve Bybit Secret
        secret = (
            os.environ.get("BYBIT_TESTNET_API_SECRET")
            or os.environ.get("BYBIT_API_SECRET")
            or data.get("BYBIT_TESTNET_API_SECRET")
            or data.get("BYBIT_API_SECRET")
            or ""
        )
        data["BYBIT_TESTNET_API_SECRET"] = secret
        data["BYBIT_API_SECRET"] = secret

        # Resolve Quantity
        if "STRATEGY_QUANTITY" in os.environ:
            data["QTY"] = float(os.environ["STRATEGY_QUANTITY"])
        elif "STRATEGY_QUANTITY" in data:
            data["QTY"] = float(data["STRATEGY_QUANTITY"])

        # Resolve Stop-Loss
        if "STOP_LOSS" in os.environ:
            data["SL_PCT"] = float(os.environ["STOP_LOSS"])
        elif "STOP_LOSS" in data:
            data["SL_PCT"] = float(data["STOP_LOSS"])

        # Resolve Take-Profit
        if "TAKE_PROFIT" in os.environ:
            data["TP_PCT"] = float(os.environ["TAKE_PROFIT"])
        elif "TAKE_PROFIT" in data:
            data["TP_PCT"] = float(data["TAKE_PROFIT"])

        return data

    model_config = {
        "extra": "ignore",
    }


settings = TradingEngineSettings()
