"""FastAPI application entrypoint for uvicorn app.main:app."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure both project root and backend directory are in sys.path
_BACKEND = Path(__file__).resolve().parent.parent
_ROOT = _BACKEND.parent

for p in (_ROOT, _BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from backend.server import app
except ImportError:
    from server import app

__all__ = ["app"]
