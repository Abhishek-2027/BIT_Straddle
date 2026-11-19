"""Application settings loaded from .env via pydantic-settings."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import model_validator

# Load .env from backend directory or project root
_BACKEND_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _BACKEND_DIR.parent

for p in (_BACKEND_DIR / ".env", _ROOT_DIR / ".env"):
    if p.exists():
        load_dotenv(p)


class Settings(BaseSettings):
    """All configuration knobs for the BTC straddle system."""

    # Bybit credentials
    BYBIT_TESTNET_API_KEY: str = ""
    BYBIT_TESTNET_API_SECRET: str = ""
    BYBIT_TESTNET: bool = False
    BYBIT_ENVIRONMENT: str = "DEMO"

    # Risk parameters
    SL_PCT: float = 0.01
    TP_PCT: float = 0.02
    QTY: float = 0.01
    MAX_SPREAD_PCT: float = 0.015

    # Timing
    STALE_QUOTE_SECS: int = 5
    EXIT_WATCHDOG_SECS: int = 10

    # Behaviour
    AUTO_ENTER: bool = False
    ENTRY_ORDER_STYLE: str = "ioc_limit"
    EXIT_ORDER_STYLE: str = "ioc_limit"
    LEG_FAIL_POLICY: str = "unwind"

    # API
    API_PORT: int = 8000

    @property
    def bybit_environment(self) -> str:
        return self.BYBIT_ENVIRONMENT

    @property
    def bybit_is_demo(self) -> bool:
        return self.BYBIT_ENVIRONMENT == "DEMO"

    @property
    def bybit_is_testnet(self) -> bool:
        return self.BYBIT_ENVIRONMENT == "TESTNET"

    @property
    def bybit_public_rest_base_url(self) -> str:
        if self.bybit_is_testnet:
            return "https://api-testnet.bybit.com"
        return "https://api.bybit.com"

    @model_validator(mode="before")
    @classmethod
    def handle_aliases(cls, data: dict):
        data = dict(data or {})
        # Prefer populated legacy names only when the environment-specific value is empty.
        for alias, canonical in (
            ("BYBIT_API_KEY", "BYBIT_TESTNET_API_KEY"),
            ("BYBIT_API_SECRET", "BYBIT_TESTNET_API_SECRET"),
        ):
            alias_value = os.environ.get(alias) or data.get(alias)
            canonical_value = os.environ.get(canonical) or data.get(canonical)
            if alias_value and not canonical_value:
                data[canonical] = alias_value

        # Allow STOP_LOSS as alias for SL_PCT
        if "STOP_LOSS" in os.environ:
            data["SL_PCT"] = float(os.environ["STOP_LOSS"])
        elif "STOP_LOSS" in data:
            data["SL_PCT"] = float(data["STOP_LOSS"])

        # Allow TAKE_PROFIT as alias for TP_PCT
        if "TAKE_PROFIT" in os.environ:
            data["TP_PCT"] = float(os.environ["TAKE_PROFIT"])
        elif "TAKE_PROFIT" in data:
            data["TP_PCT"] = float(data["TAKE_PROFIT"])

        # Allow STRATEGY_QUANTITY as alias for QTY
        if "STRATEGY_QUANTITY" in os.environ:
            data["QTY"] = float(os.environ["STRATEGY_QUANTITY"])
        elif "STRATEGY_QUANTITY" in data:
            data["QTY"] = float(data["STRATEGY_QUANTITY"])

        configured_environment = (
            os.environ.get("BYBIT_ENVIRONMENT")
            or data.get("BYBIT_ENVIRONMENT")
        )
        if configured_environment is None:
            if "BYBIT_TESTNET" in data:
                configured_environment = "TESTNET" if data["BYBIT_TESTNET"] else "MAINNET"
            else:
                configured_environment = "DEMO"
        environment = str(configured_environment).strip().upper()
        if environment not in {"TESTNET", "DEMO", "MAINNET"}:
            raise ValueError("BYBIT_ENVIRONMENT must be TESTNET, DEMO, or MAINNET")
        data["BYBIT_ENVIRONMENT"] = environment
        data["BYBIT_TESTNET"] = environment == "TESTNET"

        return data

    model_config = {
        "env_file": str(_BACKEND_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
