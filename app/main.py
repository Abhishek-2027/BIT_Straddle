"""Root-level entrypoint so `uvicorn app.main:app` works from project root."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
for p in (_ROOT, _BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from backend.server import app
except ImportError:
    from server import app

__all__ = ["app"]
