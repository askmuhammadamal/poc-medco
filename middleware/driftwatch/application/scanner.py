"""Polls scan ranges, caches previous values, emits ChangeEvents on change. One asyncio task
per range. On ILLEGAL_DATA_ADDRESS, bisects to find dead address(es), records them, and keeps
polling the surviving sub-ranges."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Sequence

from ..domain.change_event import ChangeEvent
from ..domain.exceptions import ModbusProtocolException
from .dead_tracker import DeadAddressTracker
from .ports import ChangeSink, ModbusClient
from .scan_range import ScanRange

log = logging.getLogger("driftwatch.scanner")


class ScannerService:
    def __init__(self, client: ModbusClient, ranges: Sequence[ScanRange], sink: ChangeSink,
                 dead_tracker: DeadAddressTracker) -> None:
        self._client = client
        self._ranges = list(ranges)
        self._sink = sink
        self._dead = dead_tracker
        self._last_successful_scan: Optional[datetime] = None

    @property
    def last_successful_scan(self) -> Optional[datetime]:
        return self._last_successful_scan

    async def run(self) -> None:
        if not self._ranges:
            log.warning("Scanner started with no ranges. Idle until shutdown.")
            while True:
                await asyncio.sleep(3600)
        await asyncio.gather(*(self._run_range(r) for r in self._ranges))

    async def _run_range(self, rng: ScanRange) -> None:
        cache: List[Optional[int]] = [None] * rng.count
        log.info("Range %s starting; interval=%.0fms.", rng.label, rng.poll_interval_s * 1000)
        try:
            while True:
                try:
                    await self._poll_once(rng, cache)
                    self._last_successful_scan = datetime.now().astimezone()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 — one bad cycle must not kill the loop
                    log.error("Range %s poll failed: %s", rng.label, exc)
                await asyncio.sleep(rng.poll_interval_s)
        except asyncio.CancelledError:
            log.info("Range %s stopped.", rng.label)
            raise

    async def _poll_once(self, rng: ScanRange, cache: List[Optional[int]]) -> None:
        for sub_start, sub_count in self._dead.live_sub_ranges(rng.unit_id, rng.object_type, rng.start, rng.count):
            cursor = sub_start
            remaining = sub_count
            while remaining > 0:
                batch = min(remaining, rng.max_batch_size)
                await self._read_and_emit(rng, cache, cursor, batch)
                cursor += batch
                remaining -= batch

    async def _read_and_emit(self, rng: ScanRange, cache: List[Optional[int]], start: int, count: int) -> None:
        try:
            values = await self._client.read(rng.object_type, rng.unit_id, start, count)
        except ModbusProtocolException as exc:
            if exc.is_address_invalid:
                await self._handle_illegal(rng, cache, start, count)
                return
            raise

        now = datetime.now().astimezone()
        for i in range(count):
            address = start + i
            cache_index = address - rng.start
            new_value = values[i]
            old_value = cache[cache_index]
            if old_value == new_value:
                continue
            cache[cache_index] = new_value
            await self._sink.emit(ChangeEvent(
                timestamp=now,
                unit_id=rng.unit_id,
                object_type=rng.object_type,
                address=address,
                old_value=old_value,
                new_value=new_value,
                label=rng.label,
            ))

    async def _handle_illegal(self, rng: ScanRange, cache: List[Optional[int]], start: int, count: int) -> None:
        if count == 1:
            self._dead.mark(rng.unit_id, rng.object_type, start)
            log.info("Marked dead: %s unit %s addr %s", rng.object_type.value, rng.unit_id, start)
            return
        half = count // 2
        await self._read_and_emit(rng, cache, start, half)
        await self._read_and_emit(rng, cache, start + half, count - half)
