import pytest

from driftwatch.domain.connection_state import ConnectionState
from driftwatch.domain.exceptions import ModbusProtocolException, ModbusTransportException
from driftwatch.domain.object_type import ModbusObjectType
from driftwatch.application.options import ResilienceOptions, SafetyOptions
from driftwatch.adapters.transport.resilient import ResilientModbusClient
from driftwatch.adapters.transport.safety import SafetyGuardModbusClient, WriteBlockedError
from fake_client import FakeModbusClient


def fast_resilience(max_attempts=-1):
    return ResilienceOptions(initial_backoff_ms=1, max_backoff_ms=4, backoff_multiplier=2.0,
                             jitter=False, max_attempts=max_attempts)


# ---- SafetyGuard ----
async def test_safety_blocks_writes_by_default():
    inner = FakeModbusClient()
    await inner.connect()
    guard = SafetyGuardModbusClient(inner, SafetyOptions(allow_writes=False))
    with pytest.raises(WriteBlockedError):
        await guard.write_single_register(1, 100, 42)
    # value never reached inner
    assert (1, ModbusObjectType.HOLDING_REGISTER, 100) not in inner._values


async def test_safety_allows_when_enabled():
    inner = FakeModbusClient()
    await inner.connect()
    guard = SafetyGuardModbusClient(inner, SafetyOptions(allow_writes=True))
    await guard.write_single_register(1, 100, 42)
    assert inner._values[(1, ModbusObjectType.HOLDING_REGISTER, 100)] == 42


async def test_safety_reads_always_pass():
    inner = FakeModbusClient()
    inner.seed(1, ModbusObjectType.HOLDING_REGISTER, 0, 7)
    await inner.connect()
    guard = SafetyGuardModbusClient(inner, SafetyOptions(allow_writes=False))
    assert await guard.read_holding_registers(1, 0, 1) == [7]


# ---- Resilient ----
async def test_resilient_connect_retries_then_succeeds():
    inner = FakeModbusClient()
    inner.fail_connects = 3
    client = ResilientModbusClient(inner, fast_resilience())
    await client.connect()
    assert inner.connect_calls == 4
    assert client.state == ConnectionState.CONNECTED


async def test_resilient_max_attempts_cap():
    inner = FakeModbusClient()
    inner.fail_connects = 100
    client = ResilientModbusClient(inner, fast_resilience(max_attempts=2))
    with pytest.raises(ModbusTransportException):
        await client.connect()
    assert inner.connect_calls == 2


async def test_resilient_protocol_exception_passes_through():
    inner = FakeModbusClient()  # nothing seeded → illegal address
    client = ResilientModbusClient(inner, fast_resilience())
    await client.connect()
    with pytest.raises(ModbusProtocolException) as ei:
        await client.read_holding_registers(1, 0, 1)
    assert ei.value.is_address_invalid


async def test_resilient_transport_fault_retries_once():
    inner = FakeModbusClient()
    inner.seed(1, ModbusObjectType.HOLDING_REGISTER, 0, 55)
    inner.transport_faults = 1  # first read faults, retry succeeds
    client = ResilientModbusClient(inner, fast_resilience())
    await client.connect()
    assert await client.read_holding_registers(1, 0, 1) == [55]


async def test_resilient_forwards_state_events():
    inner = FakeModbusClient()
    client = ResilientModbusClient(inner, fast_resilience())
    seen = []
    client.on_state_changed(seen.append)
    await client.connect()
    assert ConnectionState.CONNECTED in seen


# ---- composed pipeline (Safety → Resilient → Fake) ----
async def test_pipeline_compose():
    inner = FakeModbusClient()
    inner.seed(1, ModbusObjectType.HOLDING_REGISTER, 0, 9)
    client = SafetyGuardModbusClient(ResilientModbusClient(inner, fast_resilience()), SafetyOptions(False))
    await client.connect()
    assert await client.read_holding_registers(1, 0, 1) == [9]
    with pytest.raises(WriteBlockedError):
        await client.write_single_register(1, 0, 1)
