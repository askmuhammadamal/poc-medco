"""Configuration value-objects + fail-fast validation. Plain dataclasses (no framework)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..domain.object_type import ModbusObjectType


class Transport:
    TCP = "Tcp"
    RTU = "Rtu"


@dataclass
class TcpOptions:
    host: str = "127.0.0.1"
    port: int = 5020
    connect_timeout_ms: int = 5000
    read_timeout_ms: int = 3000
    write_timeout_ms: int = 3000


@dataclass
class RtuOptions:
    port_name: str = "COM3"
    baud_rate: int = 9600
    data_bits: int = 8
    parity: str = "N"          # N / E / O
    stop_bits: int = 1
    read_timeout_ms: int = 1000
    write_timeout_ms: int = 1000
    inter_frame_delay_ms: int = 4


@dataclass
class ResilienceOptions:
    initial_backoff_ms: int = 500
    max_backoff_ms: int = 30000
    backoff_multiplier: float = 2.0
    jitter: bool = True
    max_attempts: int = -1  # -1 = infinite


@dataclass
class SafetyOptions:
    allow_writes: bool = False


@dataclass
class ModbusOptions:
    transport: str = Transport.TCP
    tcp: TcpOptions = field(default_factory=TcpOptions)
    rtu: RtuOptions = field(default_factory=RtuOptions)
    unit_id: int = 1
    resilience: ResilienceOptions = field(default_factory=ResilienceOptions)
    safety: SafetyOptions = field(default_factory=SafetyOptions)


@dataclass
class ScanRangeOptions:
    object_type: ModbusObjectType = ModbusObjectType.HOLDING_REGISTER
    start: int = 0
    count: int = 100
    poll_ms: int = 500
    unit_id: int = 1
    label: Optional[str] = None
    max_batch_size: int = 100


@dataclass
class ScannerOptions:
    ranges: List[ScanRangeOptions] = field(default_factory=list)


@dataclass
class AddressRangeOptions:
    start: int = 0
    end: int = 1000


@dataclass
class DiscoveryOptions:
    enabled: bool = False
    # Empty default on purpose: config is the source of truth.
    object_types: List[ModbusObjectType] = field(default_factory=list)
    address_range: AddressRangeOptions = field(default_factory=AddressRangeOptions)
    slave_ids: List[int] = field(default_factory=list)
    scan_slaves: bool = False
    scan_slaves_max: int = 32
    batch_size: int = 50
    pause_ms: int = 20
    report_path: str = "logs/discovery.jsonl"
    periodic: bool = False
    rerun_interval_minutes: int = 60


@dataclass
class ConsoleSinkOptions:
    enabled: bool = True


@dataclass
class CsvSinkOptions:
    enabled: bool = False
    directory: str = "logs"
    file_prefix: str = "changes"
    rotate_daily: bool = True
    flush_every: int = 16


@dataclass
class SinkOptions:
    console: ConsoleSinkOptions = field(default_factory=ConsoleSinkOptions)
    csv: CsvSinkOptions = field(default_factory=CsvSinkOptions)


@dataclass
class AppConfig:
    mode: str = "Scan"  # Scan | Discover
    modbus: ModbusOptions = field(default_factory=ModbusOptions)
    scanner: ScannerOptions = field(default_factory=ScannerOptions)
    discovery: DiscoveryOptions = field(default_factory=DiscoveryOptions)
    sinks: SinkOptions = field(default_factory=SinkOptions)


class ConfigError(ValueError):
    """Raised on invalid configuration so the service fails fast at boot."""


def validate(config: AppConfig) -> None:
    m = config.modbus
    if not (0 <= m.unit_id <= 247):
        raise ConfigError(f"Modbus.UnitId must be 0..247, got {m.unit_id}.")
    if m.transport not in (Transport.TCP, Transport.RTU):
        raise ConfigError(f"Modbus.Transport must be Tcp or Rtu, got {m.transport!r}.")
    if m.tcp.port <= 0 or m.tcp.port > 65535:
        raise ConfigError(f"Modbus.Tcp.Port must be 1..65535, got {m.tcp.port}.")
    if m.resilience.backoff_multiplier < 1.0:
        raise ConfigError("Modbus.Resilience.BackoffMultiplier must be >= 1.0.")

    for i, r in enumerate(config.scanner.ranges):
        if r.poll_ms <= 0:
            raise ConfigError(f"Scanner.Ranges[{i}].PollMs must be > 0, got {r.poll_ms}.")
        if r.count <= 0:
            raise ConfigError(f"Scanner.Ranges[{i}].Count must be > 0, got {r.count}.")
        if r.max_batch_size <= 0:
            raise ConfigError(f"Scanner.Ranges[{i}].MaxBatchSize must be > 0, got {r.max_batch_size}.")
        if not (0 <= r.unit_id <= 247):
            raise ConfigError(f"Scanner.Ranges[{i}].UnitId must be 0..247, got {r.unit_id}.")

    d = config.discovery
    if d.batch_size <= 0:
        raise ConfigError(f"Discovery.BatchSize must be > 0, got {d.batch_size}.")
    if d.address_range.end < d.address_range.start:
        raise ConfigError("Discovery.AddressRange.End must be >= Start.")
