"""Shared pymodbus-backed client base for TCP + RTU. Maps pymodbus responses/exceptions onto
the protocol-vs-transport split and serializes calls on the connection.

  - pymodbus ``ExceptionResponse`` (resp.isError() with an exception_code) → ModbusProtocolException
    (code 0x02 → is_address_invalid). Connection stays healthy.
  - ConnectionException / ModbusIOException / timeout / error-response-without-code →
    ModbusTransportException + state goes Faulted.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from pymodbus.exceptions import ConnectionException, ModbusException, ModbusIOException

from ...application.ports import ModbusClient
from ...domain.connection_state import ConnectionState
from ...domain.exceptions import ModbusProtocolException, ModbusTransportException

log = logging.getLogger("driftwatch.transport")


class PymodbusClientBase(ModbusClient):
    def __init__(self) -> None:
        super().__init__()
        self._client = None  # set by subclass connect()
        self._state = ConnectionState.DISCONNECTED
        # Created lazily inside the running loop — on Python 3.9 asyncio.Lock() binds to the
        # loop at construction time, which would be the wrong loop if built before uvicorn starts.
        self._lock: Optional[asyncio.Lock] = None

    @property
    def state(self) -> ConnectionState:
        return self._state

    def _set_state(self, state: ConnectionState) -> None:
        if state != self._state:
            self._state = state
            self._notify_state(state)

    # Subclasses build self._client and return whether the connection succeeded.
    async def _open(self) -> bool:  # pragma: no cover - overridden
        raise NotImplementedError

    async def connect(self) -> None:
        self._set_state(ConnectionState.CONNECTING)
        try:
            ok = await self._open()
        except Exception as exc:  # noqa: BLE001 - normalize any open failure
            self._set_state(ConnectionState.FAULTED)
            raise ModbusTransportException(f"Connect failed: {exc}") from exc
        if not ok:
            self._set_state(ConnectionState.FAULTED)
            raise ModbusTransportException("Connect failed: client did not connect.")
        self._set_state(ConnectionState.CONNECTED)

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                pass
        self._set_state(ConnectionState.DISCONNECTED)

    def _require(self):
        if self._client is None or self._state != ConnectionState.CONNECTED:
            raise ModbusTransportException("Modbus client not connected.")
        return self._client

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def _invoke(self, fn: Callable[[], Awaitable], unit_id: int, fc: int):
        """Run one pymodbus call under the lock, mapping result/exception."""
        async with self._get_lock():
            client = self._require()
            try:
                resp = await fn(client)
            except ModbusProtocolException:
                raise
            except (ConnectionException, ModbusIOException, asyncio.TimeoutError, OSError) as exc:
                self._fault(exc)
                raise ModbusTransportException(str(exc) or type(exc).__name__) from exc
            except ModbusException as exc:
                # Other pymodbus errors — treat as transport-level to be safe.
                self._fault(exc)
                raise ModbusTransportException(str(exc)) from exc
            return self._unwrap(resp, unit_id, fc)

    def _unwrap(self, resp, unit_id: int, fc: int):
        if resp is None:
            self._fault(None)
            raise ModbusTransportException("Empty Modbus response.")
        if resp.isError():
            code = getattr(resp, "exception_code", None)
            if code is not None:
                # Real Modbus exception response — protocol level, connection stays healthy.
                raise ModbusProtocolException(code, str(resp), unit_id=unit_id, function_code=fc)
            # Error response without a code (e.g. ModbusIOException) — transport fault.
            self._fault(resp)
            raise ModbusTransportException(f"Transport error response: {resp}")
        return resp

    def _fault(self, exc: Optional[object]) -> None:
        log.warning("Transport fault, marking connection faulted: %s", exc)
        self._set_state(ConnectionState.FAULTED)

    # ---- reads ----
    async def read_coils(self, unit_id, start, count):
        resp = await self._invoke(lambda c: c.read_coils(start, count=count, slave=unit_id), unit_id, 1)
        return list(resp.bits)[:count]

    async def read_discrete_inputs(self, unit_id, start, count):
        resp = await self._invoke(lambda c: c.read_discrete_inputs(start, count=count, slave=unit_id), unit_id, 2)
        return list(resp.bits)[:count]

    async def read_holding_registers(self, unit_id, start, count):
        resp = await self._invoke(lambda c: c.read_holding_registers(start, count=count, slave=unit_id), unit_id, 3)
        return list(resp.registers)

    async def read_input_registers(self, unit_id, start, count):
        resp = await self._invoke(lambda c: c.read_input_registers(start, count=count, slave=unit_id), unit_id, 4)
        return list(resp.registers)

    # ---- writes ----
    async def write_single_coil(self, unit_id, address, value):
        await self._invoke(lambda c: c.write_coil(address, bool(value), slave=unit_id), unit_id, 5)

    async def write_multiple_coils(self, unit_id, start, values):
        await self._invoke(lambda c: c.write_coils(start, list(values), slave=unit_id), unit_id, 15)

    async def write_single_register(self, unit_id, address, value):
        await self._invoke(lambda c: c.write_register(address, int(value), slave=unit_id), unit_id, 6)

    async def write_multiple_registers(self, unit_id, start, values):
        await self._invoke(lambda c: c.write_registers(start, list(values), slave=unit_id), unit_id, 16)
