"""Build AppConfig from a built-in default, an optional YAML file, env vars, and CLI overrides.

Layering (lowest → highest precedence): built-in defaults → config.yaml → DW_* env → CLI flags.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import yaml

from ..application.options import (
    AddressRangeOptions, AppConfig, ConsoleSinkOptions, CsvSinkOptions, DiscoveryOptions,
    ResilienceOptions, RtuOptions, SafetyOptions, ScanRangeOptions, ScannerOptions,
    SinkOptions, TcpOptions, Transport,
)
from ..domain.object_type import ModbusObjectType

# Default scan ranges mirror the .NET Development appsettings so an out-of-box run against the
# simulator immediately shows changes.
_DEFAULT_RANGES = [
    ("HoldingRegister", 100, 100, 500, "HR-100"),
    ("InputRegister", 0, 16, 1000, "IR-bank"),
    ("Coil", 0, 16, 1000, "Coils-low"),
    ("DiscreteInput", 0, 32, 1000, "DI-bank"),
]


def default_config() -> AppConfig:
    cfg = AppConfig()
    cfg.scanner.ranges = [
        ScanRangeOptions(object_type=ModbusObjectType.parse(t), start=s, count=c, poll_ms=p, unit_id=1, label=lbl)
        for (t, s, c, p, lbl) in _DEFAULT_RANGES
    ]
    cfg.sinks.console.enabled = True
    cfg.sinks.csv.enabled = True
    cfg.discovery.object_types = [ModbusObjectType.parse(t) for t in
                                  ("HoldingRegister", "InputRegister", "Coil", "DiscreteInput")]
    cfg.discovery.slave_ids = [1]
    return cfg


def _apply_yaml(cfg: AppConfig, data: Dict[str, Any]) -> None:
    if not data:
        return
    cfg.mode = data.get("mode", cfg.mode)

    m = data.get("modbus") or {}
    if m:
        cfg.modbus.transport = m.get("transport", cfg.modbus.transport)
        cfg.modbus.unit_id = int(m.get("unit_id", cfg.modbus.unit_id))
        tcp = m.get("tcp") or {}
        cfg.modbus.tcp = TcpOptions(**{**vars(cfg.modbus.tcp), **tcp})
        rtu = m.get("rtu") or {}
        cfg.modbus.rtu = RtuOptions(**{**vars(cfg.modbus.rtu), **rtu})
        res = m.get("resilience") or {}
        cfg.modbus.resilience = ResilienceOptions(**{**vars(cfg.modbus.resilience), **res})
        saf = m.get("safety") or {}
        cfg.modbus.safety = SafetyOptions(**{**vars(cfg.modbus.safety), **saf})

    sc = data.get("scanner") or {}
    if "ranges" in sc:
        cfg.scanner = ScannerOptions(ranges=[
            ScanRangeOptions(
                object_type=ModbusObjectType.parse(r["object_type"]),
                start=int(r.get("start", 0)),
                count=int(r.get("count", 100)),
                poll_ms=int(r.get("poll_ms", 500)),
                unit_id=int(r.get("unit_id", 1)),
                label=r.get("label"),
                max_batch_size=int(r.get("max_batch_size", 100)),
            ) for r in sc["ranges"]
        ])

    d = data.get("discovery") or {}
    if d:
        if "object_types" in d:
            cfg.discovery.object_types = [ModbusObjectType.parse(t) for t in d["object_types"]]
        if "address_range" in d:
            cfg.discovery.address_range = AddressRangeOptions(**{**vars(cfg.discovery.address_range), **d["address_range"]})
        for key in ("enabled", "slave_ids", "scan_slaves", "scan_slaves_max", "batch_size",
                    "pause_ms", "report_path", "periodic", "rerun_interval_minutes"):
            if key in d:
                setattr(cfg.discovery, key, d[key])

    sk = data.get("sinks") or {}
    if "console" in sk:
        cfg.sinks.console = ConsoleSinkOptions(**{**vars(cfg.sinks.console), **sk["console"]})
    if "csv" in sk:
        cfg.sinks.csv = CsvSinkOptions(**{**vars(cfg.sinks.csv), **sk["csv"]})


def _apply_env(cfg: AppConfig) -> None:
    e = os.environ.get
    if e("DW_MODE"):
        cfg.mode = e("DW_MODE")
    if e("DW_TRANSPORT"):
        cfg.modbus.transport = e("DW_TRANSPORT")
    if e("DW_HOST"):
        cfg.modbus.tcp.host = e("DW_HOST")
    if e("DW_PORT"):
        cfg.modbus.tcp.port = int(e("DW_PORT"))
    if e("DW_RTU_PORT"):
        cfg.modbus.rtu.port_name = e("DW_RTU_PORT")
    if e("DW_BAUD"):
        cfg.modbus.rtu.baud_rate = int(e("DW_BAUD"))
    if e("DW_UNIT"):
        cfg.modbus.unit_id = int(e("DW_UNIT"))
    if e("DW_ALLOW_WRITES"):
        cfg.modbus.safety.allow_writes = e("DW_ALLOW_WRITES").lower() in ("1", "true", "yes")


def _apply_cli(cfg: AppConfig, cli: Dict[str, Any]) -> None:
    for k, v in (cli or {}).items():
        if v is None:
            continue
        if k == "mode":
            cfg.mode = v
        elif k == "transport":
            cfg.modbus.transport = Transport.TCP if v.lower() == "tcp" else Transport.RTU
        elif k == "host":
            cfg.modbus.tcp.host = v
        elif k == "port":
            cfg.modbus.tcp.port = int(v)
        elif k == "rtu_port":
            cfg.modbus.rtu.port_name = v
        elif k == "baud":
            cfg.modbus.rtu.baud_rate = int(v)
        elif k == "unit":
            cfg.modbus.unit_id = int(v)
        elif k == "allow_writes":
            cfg.modbus.safety.allow_writes = bool(v)
        elif k == "discovery_end":
            cfg.discovery.address_range.end = int(v)
        elif k == "scan_slaves":
            cfg.discovery.scan_slaves = bool(v)


def load_config(yaml_path: Optional[str] = None, cli: Optional[Dict[str, Any]] = None) -> AppConfig:
    cfg = default_config()
    if yaml_path and os.path.exists(yaml_path):
        with open(yaml_path, "r", encoding="utf-8") as f:
            _apply_yaml(cfg, yaml.safe_load(f) or {})
    _apply_env(cfg)
    _apply_cli(cfg, cli or {})
    return cfg
