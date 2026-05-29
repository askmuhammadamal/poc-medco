"""Runtime scan-range model derived from ScanRangeOptions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..domain.object_type import ModbusObjectType
from .options import ScanRangeOptions


@dataclass(frozen=True)
class ScanRange:
    object_type: ModbusObjectType
    start: int
    count: int
    poll_interval_s: float
    unit_id: int
    label: Optional[str] = None
    max_batch_size: int = 100

    @staticmethod
    def from_options(o: ScanRangeOptions) -> "ScanRange":
        return ScanRange(
            object_type=o.object_type,
            start=o.start,
            count=o.count,
            poll_interval_s=o.poll_ms / 1000.0,
            unit_id=o.unit_id,
            label=o.label,
            max_batch_size=o.max_batch_size,
        )
