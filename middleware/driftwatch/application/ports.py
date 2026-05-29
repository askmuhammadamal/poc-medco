"""Ports — the interfaces the application depends on, implemented by adapters.

- ``ModbusClient``: transport-agnostic Modbus master (driven port).
- ``ChangeSink``: where change events go (driven port).

Both depend only on domain types, never on a concrete framework.
"""
from __future__ import annotations

import abc
from typing import Callable, List

from ..domain.change_event import ChangeEvent
from ..domain.connection_state import ConnectionState
from ..domain.object_type import ModbusObjectType


class ModbusClient(abc.ABC):
    """Transport-agnostic Modbus master. All four object types plus single and multiple writes.
    ``unit_id`` is per-call so one client can target multiple devices on a bus."""

    def __init__(self) -> None:
        self._state_listeners: List[Callable[[ConnectionState], None]] = []

    @property
    @abc.abstractmethod
    def state(self) -> ConnectionState: ...

    def on_state_changed(self, listener: Callable[[ConnectionState], None]) -> None:
        self._state_listeners.append(listener)

    def _notify_state(self, state: ConnectionState) -> None:
        for listener in list(self._state_listeners):
            listener(state)

    @abc.abstractmethod
    async def connect(self) -> None: ...

    @abc.abstractmethod
    async def disconnect(self) -> None: ...

    @abc.abstractmethod
    async def read_coils(self, unit_id: int, start: int, count: int) -> list[bool]: ...

    @abc.abstractmethod
    async def read_discrete_inputs(self, unit_id: int, start: int, count: int) -> list[bool]: ...

    @abc.abstractmethod
    async def read_holding_registers(self, unit_id: int, start: int, count: int) -> list[int]: ...

    @abc.abstractmethod
    async def read_input_registers(self, unit_id: int, start: int, count: int) -> list[int]: ...

    @abc.abstractmethod
    async def write_single_coil(self, unit_id: int, address: int, value: bool) -> None: ...

    @abc.abstractmethod
    async def write_multiple_coils(self, unit_id: int, start: int, values: list[bool]) -> None: ...

    @abc.abstractmethod
    async def write_single_register(self, unit_id: int, address: int, value: int) -> None: ...

    @abc.abstractmethod
    async def write_multiple_registers(self, unit_id: int, start: int, values: list[int]) -> None: ...

    async def aclose(self) -> None:
        await self.disconnect()

    async def read(self, object_type: ModbusObjectType, unit_id: int, start: int, count: int) -> list[int]:
        """Read any object type, returning ints (bits as 0/1) so callers see a uniform type."""
        if object_type is ModbusObjectType.HOLDING_REGISTER:
            return await self.read_holding_registers(unit_id, start, count)
        if object_type is ModbusObjectType.INPUT_REGISTER:
            return await self.read_input_registers(unit_id, start, count)
        if object_type is ModbusObjectType.COIL:
            return [1 if b else 0 for b in await self.read_coils(unit_id, start, count)]
        if object_type is ModbusObjectType.DISCRETE_INPUT:
            return [1 if b else 0 for b in await self.read_discrete_inputs(unit_id, start, count)]
        raise ValueError(f"Unsupported object type: {object_type}")


class ChangeSink(abc.ABC):
    @abc.abstractmethod
    async def emit(self, event: ChangeEvent) -> None: ...

    async def flush(self) -> None:
        return None

    async def aclose(self) -> None:
        return None
