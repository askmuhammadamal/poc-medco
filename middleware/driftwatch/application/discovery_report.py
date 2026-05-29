"""Discovery report entities (the data a discovery run produces)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from ..domain.object_type import ModbusObjectType


@dataclass
class AliveRegister:
    address: int
    modicon: str
    value: int


@dataclass
class DeadRange:
    start: int
    end: int


@dataclass
class ErrorRange:
    start: int
    end: int
    reason: str


@dataclass
class ObjectTypeDiscovery:
    object_type: ModbusObjectType
    alive: List[AliveRegister] = field(default_factory=list)
    dead: List[DeadRange] = field(default_factory=list)
    errors: List[ErrorRange] = field(default_factory=list)


@dataclass
class UnitDiscovery:
    unit_id: int
    object_types: List[ObjectTypeDiscovery] = field(default_factory=list)


@dataclass
class DiscoveryReport:
    started_at: datetime
    completed_at: datetime | None = None
    responding_units: List[int] = field(default_factory=list)
    units: List[UnitDiscovery] = field(default_factory=list)
