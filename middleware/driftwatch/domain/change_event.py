"""One observable change in one Modbus address. Old value is None for the first observation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .modicon import ModiconAddress
from .object_type import ModbusObjectType


@dataclass(frozen=True)
class ChangeEvent:
    timestamp: datetime
    unit_id: int
    object_type: ModbusObjectType
    address: int
    old_value: Optional[int]
    new_value: int
    label: Optional[str] = None

    @property
    def modicon(self) -> str:
        return ModiconAddress.from_protocol(self.object_type, self.address).to_modicon_string()

    def __str__(self) -> str:
        if self.object_type.is_bit:
            display = "false" if self.new_value == 0 else "true"
            old = "(init)" if self.old_value is None else ("false" if self.old_value == 0 else "true")
        else:
            display = str(self.new_value)
            old = "(init)" if self.old_value is None else str(self.old_value)
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S.") + f"{self.timestamp.microsecond // 1000:03d}"
        return f"[{ts}] {self.modicon} {self.object_type.value} {self.address}: {old} -> {display}"
