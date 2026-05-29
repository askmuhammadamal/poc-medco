"""Resilience decorator: exponential backoff + jitter on connect, reconnect + single retry on
transport faults, protocol exceptions pass through untouched."""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

from ...application.options import ResilienceOptions
from ...application.ports import ModbusClient
from ...domain.connection_state import ConnectionState
from ...domain.exceptions import ModbusTransportException
from .delegating import DelegatingModbusClient

log = logging.getLogger("driftwatch.transport.resilient")

T = TypeVar("T")


class ResilientModbusClient(DelegatingModbusClient):
    def __init__(self, inner: ModbusClient, options: ResilienceOptions) -> None:
        super().__init__(inner)
        self._opts = options
        self._rng = random.Random()

    async def connect(self) -> None:
        await self._connect_with_backoff()

    async def _ensure_connected(self) -> None:
        if self._inner.state == ConnectionState.CONNECTED:
            return
        await self._connect_with_backoff()

    async def _connect_with_backoff(self) -> None:
        attempt = 0
        delay_ms = self._opts.initial_backoff_ms
        while True:
            attempt += 1
            try:
                await self._inner.connect()
                if attempt > 1:
                    log.info("Reconnected after %d attempts.", attempt)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("Connect attempt %d failed: %s", attempt, exc)
                if self._opts.max_attempts >= 0 and attempt >= self._opts.max_attempts:
                    raise
            sleep = delay_ms
            if self._opts.jitter:
                sleep = delay_ms * (0.5 + self._rng.random())
            await asyncio.sleep(sleep / 1000.0)
            delay_ms = min(self._opts.max_backoff_ms, delay_ms * self._opts.backoff_multiplier)

    async def _invoke(self, op: Callable[[], Awaitable[T]]) -> T:
        await self._ensure_connected()
        try:
            return await op()
        except ModbusTransportException:
            # Single retry after reconnect — smooths over the common stale-socket case.
            await self._ensure_connected()
            return await op()

    async def read_coils(self, unit_id, start, count):
        return await self._invoke(lambda: self._inner.read_coils(unit_id, start, count))

    async def read_discrete_inputs(self, unit_id, start, count):
        return await self._invoke(lambda: self._inner.read_discrete_inputs(unit_id, start, count))

    async def read_holding_registers(self, unit_id, start, count):
        return await self._invoke(lambda: self._inner.read_holding_registers(unit_id, start, count))

    async def read_input_registers(self, unit_id, start, count):
        return await self._invoke(lambda: self._inner.read_input_registers(unit_id, start, count))

    async def write_single_coil(self, unit_id, address, value):
        await self._invoke(lambda: self._inner.write_single_coil(unit_id, address, value))

    async def write_multiple_coils(self, unit_id, start, values):
        await self._invoke(lambda: self._inner.write_multiple_coils(unit_id, start, values))

    async def write_single_register(self, unit_id, address, value):
        await self._invoke(lambda: self._inner.write_single_register(unit_id, address, value))

    async def write_multiple_registers(self, unit_id, start, values):
        await self._invoke(lambda: self._inner.write_multiple_registers(unit_id, start, values))
