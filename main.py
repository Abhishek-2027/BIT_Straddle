"""Root-level entrypoint so `uvicorn main:app` and `python main.py` work from project root."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_BACKEND = _ROOT / "backend"
for p in (_ROOT, _BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from backend.main import app, main
except ImportError:
    from main import app, main

__all__ = ["app", "main"]

if __name__ == "__main__":
    main()
