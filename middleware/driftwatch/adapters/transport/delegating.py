"""Base decorator that forwards every ModbusClient call to an inner client and re-emits its
state changes. Resilient/Safety extend this and override only what they change."""
from __future__ import annotations

from ...application.ports import ModbusClient
from ...domain.connection_state import ConnectionState


class DelegatingModbusClient(ModbusClient):
    def __init__(self, inner: ModbusClient) -> None:
        super().__init__()
        self._inner = inner
        self._inner.on_state_changed(self._notify_state)

    @property
    def state(self) -> ConnectionState:
        return self._inner.state

    async def connect(self) -> None:
        await self._inner.connect()

    async def disconnect(self) -> None:
        await self._inner.disconnect()

    async def read_coils(self, unit_id, start, count):
        return await self._inner.read_coils(unit_id, start, count)

    async def read_discrete_inputs(self, unit_id, start, count):
        return await self._inner.read_discrete_inputs(unit_id, start, count)

    async def read_holding_registers(self, unit_id, start, count):
        return await self._inner.read_holding_registers(unit_id, start, count)

    async def read_input_registers(self, unit_id, start, count):
        return await self._inner.read_input_registers(unit_id, start, count)

    async def write_single_coil(self, unit_id, address, value):
        await self._inner.write_single_coil(unit_id, address, value)

    async def write_multiple_coils(self, unit_id, start, values):
        await self._inner.write_multiple_coils(unit_id, start, values)

    async def write_single_register(self, unit_id, address, value):
        await self._inner.write_single_register(unit_id, address, value)

    async def write_multiple_registers(self, unit_id, start, values):
        await self._inner.write_multiple_registers(unit_id, start, values)
