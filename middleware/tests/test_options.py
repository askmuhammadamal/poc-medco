import pytest

from driftwatch.application.options import (
    AppConfig, ConfigError, ModbusOptions, ScannerOptions, ScanRangeOptions,
    DiscoveryOptions, AddressRangeOptions, validate,
)


def test_defaults_validate():
    validate(AppConfig())  # no ranges, defaults — should pass


def test_bad_unit_id():
    cfg = AppConfig(modbus=ModbusOptions(unit_id=300))
    with pytest.raises(ConfigError):
        validate(cfg)


def test_bad_port():
    cfg = AppConfig(modbus=ModbusOptions())
    cfg.modbus.tcp.port = 0
    with pytest.raises(ConfigError):
        validate(cfg)


def test_bad_poll_ms():
    cfg = AppConfig(scanner=ScannerOptions(ranges=[ScanRangeOptions(poll_ms=0)]))
    with pytest.raises(ConfigError):
        validate(cfg)


def test_bad_batch_size():
    cfg = AppConfig(scanner=ScannerOptions(ranges=[ScanRangeOptions(max_batch_size=0)]))
    with pytest.raises(ConfigError):
        validate(cfg)


def test_discovery_range_inverted():
    cfg = AppConfig(discovery=DiscoveryOptions(address_range=AddressRangeOptions(start=100, end=50)))
    with pytest.raises(ConfigError):
        validate(cfg)


def test_valid_ranges_pass():
    cfg = AppConfig(scanner=ScannerOptions(ranges=[
        ScanRangeOptions(poll_ms=500, count=10, max_batch_size=100, unit_id=1),
    ]))
    validate(cfg)
