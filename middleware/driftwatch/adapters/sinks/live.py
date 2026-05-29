"""Powers the live dashboard: keeps the latest value per (unit, type, address) for the snapshot
endpoint and fans each change out to every SSE subscriber.

emit() must never block/throw — each subscriber owns a bounded queue; on overflow the oldest
event is dropped (a slow browser loses history but the snapshot gives authoritative state on
reconnect)."""
from __future__ import annotations

import asyncio
import uuid
from typing import Dict, List, Tuple

from ...application.ports import ChangeSink
from ...domain.change_event import ChangeEvent
from ...domain.object_type import ModbusObjectType

_CAPACITY = 1024
_Key = Tuple[int, ModbusObjectType, int]


class LiveStateSink(ChangeSink):
    def __init__(self) -> None:
        self._latest: Dict[_Key, ChangeEvent] = {}
        self._subscribers: Dict[str, asyncio.Queue] = {}

    async def emit(self, event: ChangeEvent) -> None:
        self._latest[(event.unit_id, event.object_type, event.address)] = event
        for queue in list(self._subscribers.values()):
            self._offer(queue, event)

    @staticmethod
    def _offer(queue: asyncio.Queue, event: ChangeEvent) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()      # drop oldest
                queue.put_nowait(event)
            except Exception:
                pass

    def snapshot(self) -> List[ChangeEvent]:
        return list(self._latest.values())

    def subscribe(self) -> Tuple[str, asyncio.Queue]:
        sub_id = uuid.uuid4().hex
        queue: asyncio.Queue = asyncio.Queue(maxsize=_CAPACITY)
        self._subscribers[sub_id] = queue
        return sub_id, queue

    def unsubscribe(self, sub_id: str) -> None:
        self._subscribers.pop(sub_id, None)
