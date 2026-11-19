"""
Thread-safe bridge between NautilusTrader event loop and FastAPI server.

Uses queue.Queue for bidirectional communication:
  - event_queue: strategy → server (events, snapshots)
  - command_queue: server → strategy (ARM, DISARM, FLATTEN, UPDATE_CONFIG)
"""
from __future__ import annotations

import queue
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventBridge:
    """Thread-safe, queue-based bridge between the trading strategy and the API server."""

    def __init__(self) -> None:
        # strategy → server: JSON-serializable dicts (events + snapshots)
        self.event_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=2048)
        # server → strategy: command dicts
        self.command_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=256)
        # latest snapshot for new WS clients / GET /api/state
        self._latest_snapshot: dict[str, Any] | None = None
        # ring buffer of recent events
        self._recent_events: list[dict[str, Any]] = []

    # ── strategy → server ──────────────────────────────────────────────

    def push_event(self, event: dict[str, Any]) -> None:
        """Push a strategy event onto the event queue (non-blocking, drops if full)."""
        self._recent_events.append(event)
        if len(self._recent_events) > 300:
            self._recent_events.pop(0)
        try:
            self.event_queue.put_nowait(event)
        except queue.Full:
            logger.warning("EventBridge: event_queue full – dropping event %s", event.get("code", "?"))

    @property
    def recent_events(self) -> list[dict[str, Any]]:
        return list(self._recent_events)

    def push_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Push a snapshot onto the event queue and cache it for late joiners."""
        snapshot.setdefault("type", "snapshot")
        self._latest_snapshot = snapshot
        try:
            self.event_queue.put_nowait(snapshot)
        except queue.Full:
            logger.warning("EventBridge: event_queue full – dropping snapshot")

    @property
    def latest_snapshot(self) -> dict[str, Any] | None:
        return self._latest_snapshot

    def get_events(self, timeout: float = 0.1) -> list[dict[str, Any]]:
        """Drain all pending events, blocking up to *timeout* seconds for the first one."""
        events: list[dict[str, Any]] = []
        try:
            events.append(self.event_queue.get(timeout=timeout))
        except queue.Empty:
            return events
        # Drain whatever else is available without blocking
        while True:
            try:
                events.append(self.event_queue.get_nowait())
            except queue.Empty:
                break
        return events

    # ── server → strategy ──────────────────────────────────────────────

    def push_command(self, command: dict[str, Any]) -> None:
        """Push a command from the server into the command queue."""
        try:
            self.command_queue.put_nowait(command)
        except queue.Full:
            logger.warning("EventBridge: command_queue full – dropping command %s", command.get("command", "?"))

    def drain_commands(self) -> list[dict[str, Any]]:
        """Return all pending commands (non-blocking)."""
        commands: list[dict[str, Any]] = []
        while True:
            try:
                commands.append(self.command_queue.get_nowait())
            except queue.Empty:
                break
        return commands


# ── Singleton (process-wide across all import paths) ────────────────────
import sys

if hasattr(sys, "_btc_straddle_bridge"):
    bridge = sys._btc_straddle_bridge
else:
    bridge = EventBridge()
    sys._btc_straddle_bridge = bridge

# Alias sys.modules so 'bridge' and 'backend.bridge' resolve to the same module
sys.modules["bridge"] = sys.modules.get("backend.bridge", sys.modules.get("bridge"))
sys.modules["backend.bridge"] = sys.modules["bridge"]
