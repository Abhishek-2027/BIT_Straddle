"""Tests for EventBridge and FastAPI endpoints in backend.server."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from backend.bridge import EventBridge
from backend import server
from backend.server import app, bridge
from backend.models import StrategyState


def test_bridge_queues():
    test_bridge = EventBridge()

    # Test event queue
    event = {"type": "event", "code": "TEST", "text": "Testing bridge"}
    test_bridge.push_event(event)
    events = test_bridge.get_events(timeout=0.05)
    assert len(events) == 1
    assert events[0]["code"] == "TEST"

    # Test snapshot caching
    snapshot = {"state": "QUOTING", "quotes": {}}
    test_bridge.push_snapshot(snapshot)
    assert test_bridge.latest_snapshot is not None
    assert test_bridge.latest_snapshot["state"] == "QUOTING"
    assert test_bridge.latest_snapshot["type"] == "snapshot"

    # Test command queue
    test_bridge.push_command({"command": "ARM"})
    test_bridge.push_command({"command": "DISARM"})
    commands = test_bridge.drain_commands()
    assert len(commands) == 2
    assert commands[0]["command"] == "ARM"
    assert commands[1]["command"] == "DISARM"
    assert len(test_bridge.drain_commands()) == 0


def test_api_health_endpoint():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "trading_node" in response.json()


def test_cors_allows_vite_fallback_port():
    cors_config = next(
        middleware.kwargs
        for middleware in app.user_middleware
        if middleware.cls is CORSMiddleware
    )
    origin_pattern = cors_config["allow_origin_regex"]

    assert re.fullmatch(origin_pattern, "http://localhost:5174")
    assert re.fullmatch(origin_pattern, "http://127.0.0.1:5180")


def test_api_state_endpoint():
    client = TestClient(app)
    bridge._latest_snapshot = {"state": "ARMED", "selection": None}
    response = client.get("/api/state")
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "ARMED"


def test_api_state_does_not_restore_snapshot_from_previous_process(monkeypatch):
    monkeypatch.setattr(bridge, "_latest_snapshot", None)
    monkeypatch.setattr(
        server,
        "_trading_status",
        {"state": "starting", "message": "Waiting for current startup."},
    )

    response = server._current_snapshot()

    assert response["state"] == "STARTING"
    assert response["node_status"] == "starting"
    assert response["node_message"] == "Waiting for current startup."


def test_api_arm_disarm_flatten_endpoints(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(server, "_trading_status", {"state": "ready", "message": None})

    # Clear pending commands
    bridge.drain_commands()

    # ARM
    r = client.post("/api/arm")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "command": "ARM"}

    # DISARM
    r = client.post("/api/disarm")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "command": "DISARM"}

    # FLATTEN
    r = client.post("/api/flatten")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "command": "FLATTEN"}

    cmds = bridge.drain_commands()
    assert len(cmds) == 3
    assert [c["command"] for c in cmds] == ["ARM", "DISARM", "FLATTEN"]


def test_api_arm_rejects_when_trading_node_is_not_ready(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(
        server,
        "_trading_status",
        {"state": "error", "message": "NautilusTrader failed to start."},
    )
    bridge.drain_commands()

    response = client.post("/api/arm")

    assert response.status_code == 503
    assert response.json()["detail"] == "NautilusTrader failed to start."
    assert bridge.drain_commands() == []


def test_api_config_endpoint():
    client = TestClient(app)
    bridge.drain_commands()

    # In idle or quoting state, config update succeeds
    bridge._latest_snapshot = {"state": "IDLE"}
    r = client.post("/api/config", json={"sl_pct": 0.015, "tp_pct": 0.025})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["updated"]["sl_pct"] == 0.015
    assert data["updated"]["tp_pct"] == 0.025

    cmds = bridge.drain_commands()
    assert len(cmds) == 1
    assert cmds[0]["command"] == "UPDATE_CONFIG"
    assert cmds[0]["payload"]["sl_pct"] == 0.015

    # If position is OPEN, config update is rejected with 400
    bridge._latest_snapshot = {"state": "OPEN"}
    r_bad = client.post("/api/config", json={"qty": 0.02})
    assert r_bad.status_code == 400
    assert "Cannot update config while strategy state is 'OPEN'" in r_bad.json()["detail"]


def test_account_balance_endpoint_is_not_part_of_the_assignment_api():
    response = TestClient(app).get("/api/account/balance")

    assert response.status_code == 404
