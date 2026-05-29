import asyncio

import pytest

from driftwatch.domain.object_type import ModbusObjectType
from driftwatch.domain.change_event import ChangeEvent
from driftwatch.application.dead_tracker import DeadAddressTracker
from driftwatch.application.scan_range import ScanRange
from driftwatch.application.scanner import ScannerService
from driftwatch.application.ports import ChangeSink
from fake_client import FakeModbusClient

HR = ModbusObjectType.HOLDING_REGISTER
IR = ModbusObjectType.INPUT_REGISTER
COIL = ModbusObjectType.COIL


class RecordingSink(ChangeSink):
    def __init__(self):
        self.events: list[ChangeEvent] = []

    async def emit(self, event: ChangeEvent) -> None:
        self.events.append(event)


def rng(otype, start, count, poll_ms=10, unit=1, label=None):
    return ScanRange(otype, start, count, poll_ms / 1000.0, unit, label)


async def run_for(scanner: ScannerService, seconds: float):
    task = asyncio.create_task(scanner.run())
    await asyncio.sleep(seconds)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_first_pass_emits_init():
    client = FakeModbusClient()
    client.seed_range(1, HR, 0, 10, 20, 30)
    await client.connect()
    sink = RecordingSink()
    scanner = ScannerService(client, [rng(HR, 0, 3)], sink, DeadAddressTracker())
    await run_for(scanner, 0.05)

    inits = [e for e in sink.events if e.old_value is None]
    assert len(inits) == 3
    assert {(e.address, e.new_value) for e in inits} == {(0, 10), (1, 20), (2, 30)}


async def test_unchanged_no_further_emit():
    client = FakeModbusClient()
    client.seed_range(1, HR, 0, 5, 5, 5)
    await client.connect()
    sink = RecordingSink()
    scanner = ScannerService(client, [rng(HR, 0, 3, poll_ms=5)], sink, DeadAddressTracker())
    await run_for(scanner, 0.06)
    assert len([e for e in sink.events if e.old_value is not None]) == 0


async def test_change_detected_emits_delta():
    client = FakeModbusClient()
    client.seed_range(1, HR, 0, 100, 200)
    await client.connect()
    sink = RecordingSink()
    scanner = ScannerService(client, [rng(HR, 0, 2)], sink, DeadAddressTracker())
    task = asyncio.create_task(scanner.run())
    await asyncio.sleep(0.03)
    client.set_value(1, HR, 1, 250)
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert any(e.address == 1 and e.old_value == 200 and e.new_value == 250 for e in sink.events)


async def test_illegal_address_marks_dead_and_continues():
    client = FakeModbusClient()
    client.seed(1, HR, 0, 11)
    client.seed(1, HR, 1, 12)
    client.seed(1, HR, 3, 14)  # addr 2 missing → illegal
    await client.connect()
    sink = RecordingSink()
    tracker = DeadAddressTracker()
    scanner = ScannerService(client, [rng(HR, 0, 4)], sink, tracker)
    await run_for(scanner, 0.06)

    assert tracker.is_dead(1, HR, 2)
    addrs = {(e.address, e.new_value) for e in sink.events}
    assert {(0, 11), (1, 12), (3, 14)}.issubset(addrs)


async def test_multiple_ranges_independent():
    client = FakeModbusClient()
    client.seed_range(1, HR, 0, 1, 2)
    client.seed_range(1, IR, 0, 9, 8)
    await client.connect()
    sink = RecordingSink()
    scanner = ScannerService(client, [rng(HR, 0, 2, label="HR"), rng(IR, 0, 2, label="IR")], sink, DeadAddressTracker())
    await run_for(scanner, 0.05)
    assert any(e.object_type == HR and e.new_value == 1 for e in sink.events)
    assert any(e.object_type == IR and e.new_value == 9 for e in sink.events)


async def test_coil_change_boolean():
    client = FakeModbusClient()
    client.seed(1, COIL, 0, 1)
    await client.connect()
    sink = RecordingSink()
    scanner = ScannerService(client, [rng(COIL, 0, 1)], sink, DeadAddressTracker())
    task = asyncio.create_task(scanner.run())
    await asyncio.sleep(0.03)
    client.set_value(1, COIL, 0, 0)
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert any(e.object_type == COIL and e.old_value == 1 and e.new_value == 0 for e in sink.events)


def test_dead_tracker_live_subranges():
    t = DeadAddressTracker()
    t.mark(1, HR, 2)
    t.mark(1, HR, 5)
    runs = list(t.live_sub_ranges(1, HR, 0, 8))
    assert runs == [(0, 2), (3, 2), (6, 2)]
    # fully dead
    t2 = DeadAddressTracker()
    for a in range(3):
        t2.mark(1, HR, a)
    assert list(t2.live_sub_ranges(1, HR, 0, 3)) == []
