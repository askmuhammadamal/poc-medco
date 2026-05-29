"""Tracks addresses that returned ILLEGAL_DATA_ADDRESS, keyed per (unit, object type, address).
An address dead on unit 1 may be live on unit 2."""
from __future__ import annotations

from typing import Dict, Iterator, Set, Tuple

from ..domain.object_type import ModbusObjectType


class DeadAddressTracker:
    def __init__(self) -> None:
        self._dead: Dict[Tuple[int, ModbusObjectType], Set[int]] = {}

    def mark(self, unit_id: int, object_type: ModbusObjectType, address: int) -> None:
        self._dead.setdefault((unit_id, object_type), set()).add(address)

    def is_dead(self, unit_id: int, object_type: ModbusObjectType, address: int) -> bool:
        return address in self._dead.get((unit_id, object_type), ())

    def live_sub_ranges(self, unit_id: int, object_type: ModbusObjectType, start: int, count: int
                        ) -> Iterator[Tuple[int, int]]:
        """Yield (sub_start, sub_count) for each contiguous run of non-dead addresses in
        [start, start+count). Dead addresses split the range; fully-dead → nothing yielded."""
        dead = self._dead.get((unit_id, object_type), ())
        run_start = None
        for addr in range(start, start + count):
            if addr in dead:
                if run_start is not None:
                    yield run_start, addr - run_start
                    run_start = None
            else:
                if run_start is None:
                    run_start = addr
        if run_start is not None:
            yield run_start, start + count - run_start
