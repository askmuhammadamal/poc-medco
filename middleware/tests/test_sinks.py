import csv
from datetime import datetime

import pytest

from driftwatch.domain.object_type import ModbusObjectType
from driftwatch.application.options import CsvSinkOptions
from driftwatch.domain.change_event import ChangeEvent
from driftwatch.adapters.sinks.csv_sink import CsvSink, HEADER
from driftwatch.adapters.sinks.live import LiveStateSink

HR = ModbusObjectType.HOLDING_REGISTER
COIL = ModbusObjectType.COIL


def evt(addr, old, new, otype=HR, unit=1):
    return ChangeEvent(datetime(2026, 5, 29, 9, 0, 0), unit, otype, addr, old, new, "lbl")


# ---- LiveStateSink ----
async def test_live_snapshot_latest_wins():
    live = LiveStateSink()
    await live.emit(evt(100, None, 10))
    await live.emit(evt(100, 10, 20))
    await live.emit(evt(101, None, 5))
    snap = {e.address: e.new_value for e in live.snapshot()}
    assert snap == {100: 20, 101: 5}


async def test_live_distinct_keys():
    live = LiveStateSink()
    await live.emit(evt(0, None, 1, otype=HR, unit=1))
    await live.emit(evt(0, None, 2, otype=HR, unit=2))
    await live.emit(evt(0, None, 1, otype=COIL, unit=1))
    assert len(live.snapshot()) == 3


async def test_live_subscribe_unsubscribe():
    live = LiveStateSink()
    sub_id, q = live.subscribe()
    await live.emit(evt(1, None, 7))
    assert q.get_nowait().new_value == 7
    live.unsubscribe(sub_id)
    await live.emit(evt(1, 7, 8))
    assert q.empty()


async def test_live_slow_subscriber_never_blocks():
    live = LiveStateSink()
    live.subscribe()  # never drained
    for i in range(5000):  # past the 1024 capacity
        await live.emit(evt(1, None, i % 100))  # must not raise/block


# ---- CsvSink ----
async def test_csv_writes_header_and_rows(tmp_path):
    opts = CsvSinkOptions(enabled=True, directory=str(tmp_path), file_prefix="changes",
                          rotate_daily=True, flush_every=1)
    sink = CsvSink(opts)
    await sink.emit(evt(100, None, 1234))
    await sink.emit(evt(100, 1234, 1235))
    await sink.aclose()

    path = tmp_path / "changes-2026-05-29.csv"
    rows = list(csv.reader(open(path)))
    assert rows[0] == HEADER
    assert rows[1][:5] == ["2026-05-29T09:00:00", "1", "HoldingRegister", "100", "40101"]
    assert rows[1][5] == ""          # old_value None → empty
    assert rows[1][6] == "1234"
    assert rows[2][5] == "1234"
