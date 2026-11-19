"""
Main entry point for the BTC ATM Short Straddle Trading System.

Supports multiple execution modes:
1. Uvicorn CLI (app.main:app):
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

2. Uvicorn CLI (main:app):
   uvicorn main:app --reload --host 0.0.0.0 --port 8000

3. Python script:
   python main.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure root and backend directories are in sys.path
_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = Path(__file__).resolve().parent
for p in (_ROOT, _BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import uvicorn
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv(_BACKEND / ".env")

try:
    from backend.config import settings
    from backend.server import app
except ImportError:
    from config import settings
    from server import app

# Expose app for `uvicorn main:app`
__all__ = ["app", "main"]

logger = logging.getLogger("btc_straddle")


def main() -> None:
    """Run uvicorn server directly when invoked as a script."""
    logger.info("Starting BTC ATM Short Straddle on http://0.0.0.0:%d", settings.API_PORT)
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.API_PORT,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
