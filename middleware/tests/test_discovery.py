import json

import pytest

from driftwatch.domain.object_type import ModbusObjectType
from driftwatch.application.options import AddressRangeOptions, DiscoveryOptions
from driftwatch.application.discovery import AddressDiscoveryService
from driftwatch.application.slave_scanner import SlaveScanner
from driftwatch.application.discovery_report import (
    DiscoveryReport, ObjectTypeDiscovery, UnitDiscovery, AliveRegister, DeadRange,
)
from driftwatch.adapters.discovery_report_writer import write_report
from fake_client import FakeModbusClient

HR = ModbusObjectType.HOLDING_REGISTER


def disco_opts(**kw):
    o = DiscoveryOptions(
        object_types=[HR],
        address_range=AddressRangeOptions(start=0, end=5),
        slave_ids=[1],
        batch_size=50,
        pause_ms=0,
    )
    for k, v in kw.items():
        setattr(o, k, v)
    return o


async def test_classify_alive_and_dead_multi():
    client = FakeModbusClient()
    # addresses 0,1,2,4 alive; 3 and 5 missing → dead (multi-dead bisection)
    for a, v in [(0, 10), (1, 11), (2, 12), (4, 14)]:
        client.seed(1, HR, a, v)
    await client.connect()
    svc = AddressDiscoveryService(client, disco_opts(), SlaveScanner(client))
    report = await svc.run()

    ot = report.units[0].object_types[0]
    assert sorted(a.address for a in ot.alive) == [0, 1, 2, 4]
    dead_addrs = sorted(d.start for d in ot.dead)
    assert dead_addrs == [3, 5]
    assert report.responding_units == [1]


async def test_all_alive_no_dead():
    client = FakeModbusClient()
    for a in range(6):
        client.seed(1, HR, a, a * 2)
    await client.connect()
    svc = AddressDiscoveryService(client, disco_opts(), SlaveScanner(client))
    report = await svc.run()
    ot = report.units[0].object_types[0]
    assert len(ot.alive) == 6
    assert ot.dead == []


async def test_slave_scanner_classifies():
    client = FakeModbusClient()
    client.seed(1, HR, 0, 1)          # unit 1 responds with data
    client.silent_units.add(2)        # unit 2 absent (transport fault)
    # unit 3: not seeded, not silent → illegal address = responds with exception
    await client.connect()
    responders = await SlaveScanner(client).scan(3)
    assert responders == [1, 3]


async def test_scan_slaves_used_when_enabled():
    client = FakeModbusClient()
    client.seed(1, HR, 0, 7)
    client.silent_units.update({2, 3})
    await client.connect()
    svc = AddressDiscoveryService(client, disco_opts(scan_slaves=True, scan_slaves_max=3), SlaveScanner(client))
    report = await svc.run()
    assert report.responding_units == [1]


def test_write_report_jsonl(tmp_path, monkeypatch):
    from datetime import datetime
    monkeypatch.chdir(tmp_path)  # relative report path → timestamped name (rooted paths are used as-is)
    report = DiscoveryReport(started_at=datetime(2026, 5, 29, 8, 0, 0),
                             completed_at=datetime(2026, 5, 29, 8, 0, 1),
                             responding_units=[1])
    unit = UnitDiscovery(unit_id=1)
    ot = ObjectTypeDiscovery(object_type=HR)
    ot.alive.append(AliveRegister(0, "40001", 1234))
    ot.dead.append(DeadRange(3, 3))
    unit.object_types.append(ot)
    report.units.append(unit)

    path = write_report("logs/discovery.jsonl", report, now=datetime(2026, 5, 29, 8, 0, 1))
    assert path.endswith("discovery-20260529-080001.jsonl")

    lines = [json.loads(l) for l in open(path) if l.strip()]
    assert lines[0]["kind"] == "summary"
    assert lines[0]["respondingUnits"] == [1]
    assert lines[0]["durationMs"] == 1000
    assert lines[1]["kind"] == "object_type"
    assert lines[1]["objectType"] == "HoldingRegister"
    assert lines[1]["aliveCount"] == 1
    assert lines[1]["alive"][0] == {"address": 0, "modicon": "40001", "value": 1234}
    assert lines[1]["dead"][0] == {"start": 3, "end": 3}
