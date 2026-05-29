"""Safety guard decorator (outermost). When allow_writes is false, every write raises before
reaching the wire; reads pass through."""
from __future__ import annotations

import logging

from ...application.options import SafetyOptions
from ...application.ports import ModbusClient
from .delegating import DelegatingModbusClient

log = logging.getLogger("driftwatch.transport.safety")


class WriteBlockedError(Exception):
    """Raised when a write is attempted while AllowWrites is false."""


class SafetyGuardModbusClient(DelegatingModbusClient):
    def __init__(self, inner: ModbusClient, options: SafetyOptions) -> None:
        super().__init__(inner)
        self._safety = options

    @property
    def allow_writes(self) -> bool:
        return self._safety.allow_writes

    def _guard(self, operation: str, unit_id: int, address: int) -> None:
        if self._safety.allow_writes:
            return
        log.error(
            "Write blocked by safety guard: %s unit=%s addr=%s. Set Modbus.Safety.AllowWrites=true to allow.",
            operation, unit_id, address,
        )
        raise WriteBlockedError(
            f"Write blocked by safety guard: {operation} (unit {unit_id}, address {address}). "
            "Modbus.Safety.AllowWrites is false. Flip to true only after deliberate review."
        )

    async def write_single_coil(self, unit_id, address, value):
        self._guard("write_single_coil", unit_id, address)
        await self._inner.write_single_coil(unit_id, address, value)

    async def write_multiple_coils(self, unit_id, start, values):
        self._guard("write_multiple_coils", unit_id, start)
        await self._inner.write_multiple_coils(unit_id, start, values)

    async def write_single_register(self, unit_id, address, value):
        self._guard("write_single_register", unit_id, address)
        await self._inner.write_single_register(unit_id, address, value)

    async def write_multiple_registers(self, unit_id, start, values):
        self._guard("write_multiple_registers", unit_id, start)
        await self._inner.write_multiple_registers(unit_id, start, values)
