from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from driftwatch.domain.object_type import ModbusObjectType
from driftwatch.infrastructure.api import AppState, create_app
from driftwatch.infrastructure.config_loader import default_config
from driftwatch.application.options import SafetyOptions
from driftwatch.domain.change_event import ChangeEvent
from driftwatch.adapters.sinks.live import LiveStateSink
from driftwatch.adapters.transport.safety import SafetyGuardModbusClient
from fake_client import FakeModbusClient

STATIC = Path(__file__).parent.parent / "static"
HR = ModbusObjectType.HOLDING_REGISTER


def build(allow_writes: bool):
    cfg = default_config()
    cfg.modbus.safety.allow_writes = allow_writes
    inner = FakeModbusClient()
    client = SafetyGuardModbusClient(inner, SafetyOptions(allow_writes=allow_writes))
    live = LiveStateSink()
    state = AppState(live=live, client=client, config=cfg, scanner=None)
    return create_app(state, STATIC), live, inner


def test_state_config_health():
    app, live, _ = build(False)
    with TestClient(app) as c:
        assert c.get("/api/state").json() == []  # nothing emitted yet

        body = c.get("/api/config").json()
        assert body["transport"] == "Tcp"
        assert body["allowWrites"] is False
        assert len(body["ranges"]) == 4

        h = c.get("/api/health").json()
        assert h["allowWrites"] is False
        assert "connectionState" in h


def test_write_blocked_returns_403():
    app, _, _ = build(False)
    with TestClient(app) as c:
        r = c.post("/api/write", json={"unitId": 1, "objectType": "HoldingRegister",
                                       "address": 100, "value": 1234, "confirm": True})
        assert r.status_code == 403
        assert r.json()["allowWrites"] is False


def test_write_requires_confirm():
    app, _, _ = build(True)
    with TestClient(app) as c:
        r = c.post("/api/write", json={"unitId": 1, "objectType": "HoldingRegister",
                                       "address": 100, "value": 1, "confirm": False})
        assert r.status_code == 400


def test_write_read_only_type_rejected():
    app, _, _ = build(True)
    with TestClient(app) as c:
        r = c.post("/api/write", json={"unitId": 1, "objectType": "DiscreteInput",
                                       "address": 0, "value": 1, "confirm": True})
        assert r.status_code == 400


def test_write_ok_when_enabled():
    app, _, inner = build(True)
    with TestClient(app) as c:
        r = c.post("/api/write", json={"unitId": 1, "objectType": "HoldingRegister",
                                       "address": 100, "value": 4242, "confirm": True})
        assert r.status_code == 200
        assert r.json()["modicon"] == "40101"
    assert inner._values[(1, HR, 100)] == 4242


def test_discovery_204_when_no_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app, _, _ = build(False)
    with TestClient(app) as c:
        r = c.get("/api/discovery")
        assert r.status_code == 204
