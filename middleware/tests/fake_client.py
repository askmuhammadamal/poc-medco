"""In-memory ModbusClient for tests — no sockets. Port of the .NET FakeModbusClient.

Seed values per (unit, type, address); reads of a range raise ILLEGAL_DATA_ADDRESS if any
requested address is unseeded (so the scanner/discovery bisection logic is exercised).
Optional fault injection drives the resilience tests.
"""
from __future__ import annotations

from driftwatch.application.ports import ModbusClient
from driftwatch.domain.connection_state import ConnectionState
from driftwatch.domain.exceptions import ModbusProtocolException, ModbusTransportException
from driftwatch.domain.object_type import ModbusObjectType


class FakeModbusClient(ModbusClient):
    def __init__(self) -> None:
        super().__init__()
        self._values: dict[tuple[int, ModbusObjectType, int], int] = {}
        self._state = ConnectionState.DISCONNECTED
        # fault injection
        self.fail_connects = 0          # number of connect() calls to fail before succeeding
        self.transport_faults = 0       # number of read calls to fault before succeeding
        self.connect_calls = 0
        self.silent_units: set[int] = set()  # units that never respond (transport fault)

    # ---- seeding ----
    def seed(self, unit_id, object_type, address, value):
        self._values[(unit_id, object_type, address)] = int(value)

    def seed_range(self, unit_id, object_type, start, *values):
        for i, v in enumerate(values):
            self.seed(unit_id, object_type, start + i, int(v))

    def set_value(self, unit_id, object_type, address, value):
        self._values[(unit_id, object_type, address)] = int(value)

    # ---- client ----
    @property
    def state(self) -> ConnectionState:
        return self._state

    def _set_state(self, s):
        if s != self._state:
            self._state = s
            self._notify_state(s)

    async def connect(self) -> None:
        self.connect_calls += 1
        if self.fail_connects > 0:
            self.fail_connects -= 1
            self._set_state(ConnectionState.FAULTED)
            raise ModbusTransportException("fake connect failure")
        self._set_state(ConnectionState.CONNECTED)

    async def disconnect(self) -> None:
        self._set_state(ConnectionState.DISCONNECTED)

    def _maybe_fault(self):
        if self.transport_faults > 0:
            self.transport_faults -= 1
            self._set_state(ConnectionState.FAULTED)
            raise ModbusTransportException("fake transport fault")

    def _read_words(self, unit_id, object_type, start, count):
        if unit_id in self.silent_units:
            raise ModbusTransportException(f"unit {unit_id} silent")
        self._maybe_fault()
        out = []
        for i in range(count):
            key = (unit_id, object_type, start + i)
            if key not in self._values:
                raise ModbusProtocolException(0x02, "illegal data address", unit_id=unit_id)
            out.append(self._values[key])
        return out

    async def read_coils(self, unit_id, start, count):
        return [v != 0 for v in self._read_words(unit_id, ModbusObjectType.COIL, start, count)]

    async def read_discrete_inputs(self, unit_id, start, count):
        return [v != 0 for v in self._read_words(unit_id, ModbusObjectType.DISCRETE_INPUT, start, count)]

    async def read_holding_registers(self, unit_id, start, count):
        return self._read_words(unit_id, ModbusObjectType.HOLDING_REGISTER, start, count)

    async def read_input_registers(self, unit_id, start, count):
        return self._read_words(unit_id, ModbusObjectType.INPUT_REGISTER, start, count)

    async def write_single_coil(self, unit_id, address, value):
        self.set_value(unit_id, ModbusObjectType.COIL, address, 1 if value else 0)

    async def write_multiple_coils(self, unit_id, start, values):
        for i, v in enumerate(values):
            self.set_value(unit_id, ModbusObjectType.COIL, start + i, 1 if v else 0)

    async def write_single_register(self, unit_id, address, value):
        self.set_value(unit_id, ModbusObjectType.HOLDING_REGISTER, address, value)

    async def write_multiple_registers(self, unit_id, start, values):
        for i, v in enumerate(values):
            self.set_value(unit_id, ModbusObjectType.HOLDING_REGISTER, start + i, v)
