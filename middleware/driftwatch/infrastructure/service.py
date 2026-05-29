"""Composition root: wires the pipeline + sinks + scanner/discovery and hosts the FastAPI app.

Lifespan: connect the client, then either launch one scanner task per range (Scan) or run a
one-shot discovery + write the report (Discover). Shutdown cancels tasks, flushes sinks,
disconnects."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from pathlib import Path
from typing import List

import uvicorn

from ..adapters.discovery_report_writer import write_report
from ..adapters.sinks.composite import CompositeSink
from ..adapters.sinks.console import ConsoleSink
from ..adapters.sinks.csv_sink import CsvSink
from ..adapters.sinks.live import LiveStateSink
from ..adapters.transport.resilient import ResilientModbusClient
from ..adapters.transport.rtu import RtuModbusClient
from ..adapters.transport.safety import SafetyGuardModbusClient
from ..adapters.transport.tcp import TcpModbusClient
from ..application.discovery import AddressDiscoveryService
from ..application.options import AppConfig, Transport, validate
from ..application.dead_tracker import DeadAddressTracker
from ..application.scan_range import ScanRange
from ..application.scanner import ScannerService
from ..application.slave_scanner import SlaveScanner
from .api import AppState, create_app

log = logging.getLogger("driftwatch.service")

# infrastructure/service.py → driftwatch → middleware (and /app in Docker): static/ lives there.
STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


def build_client(config: AppConfig):
    if config.modbus.transport == Transport.RTU:
        concrete = RtuModbusClient(config.modbus)
    else:
        concrete = TcpModbusClient(config.modbus)
    resilient = ResilientModbusClient(concrete, config.modbus.resilience)
    return SafetyGuardModbusClient(resilient, config.modbus.safety)


def build_sink(config: AppConfig, live: LiveStateSink) -> CompositeSink:
    sinks: List = []
    if config.sinks.console.enabled:
        sinks.append(ConsoleSink())
    if config.sinks.csv.enabled:
        sinks.append(CsvSink(config.sinks.csv))
    sinks.append(live)  # always — powers the dashboard
    return CompositeSink(sinks)


def _preflight(config: AppConfig) -> None:
    m = config.modbus
    where = f"Tcp {m.tcp.host}:{m.tcp.port}" if m.transport == Transport.TCP else f"Rtu {m.rtu.port_name}@{m.rtu.baud_rate}"
    writes = "ENABLED" if m.safety.allow_writes else "disabled"
    log.info("PREFLIGHT mode=%s transport=(%s) unit=%s writes=%s ranges=%d",
             config.mode, where, m.unit_id, writes, len(config.scanner.ranges))
    if m.safety.allow_writes:
        log.warning("WRITES ARE ENABLED. Any write reaches the PLC.")


def make_app(config: AppConfig):
    validate(config)
    _preflight(config)

    live = LiveStateSink()
    client = build_client(config)
    sink = build_sink(config, live)
    is_discover = config.mode.strip().lower() == "discover"

    scanner = None
    if not is_discover:
        ranges = [ScanRange.from_options(r) for r in config.scanner.ranges]
        scanner = ScannerService(client, ranges, sink, DeadAddressTracker())

    state = AppState(live=live, client=client, config=config, scanner=scanner)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        await client.connect()
        tasks: List[asyncio.Task] = []
        if is_discover:
            tasks.append(asyncio.create_task(_run_discovery(config, client)))
        else:
            tasks.append(asyncio.create_task(scanner.run()))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
            with contextlib.suppress(Exception):
                await sink.flush()
                await sink.aclose()
            with contextlib.suppress(Exception):
                await client.disconnect()

    return create_app(state, STATIC_DIR, lifespan=lifespan)


async def _run_discovery(config: AppConfig, client) -> None:
    svc = AddressDiscoveryService(client, config.discovery, SlaveScanner(client))
    report = await svc.run()
    path = write_report(config.discovery.report_path, report, now=datetime.utcnow())
    alive = sum(len(ot.alive) for u in report.units for ot in u.object_types)
    dead = sum(len(ot.dead) for u in report.units for ot in u.object_types)
    log.info("Discovery report written to %s (units=%d alive=%d dead=%d)",
             path, len(report.responding_units), alive, dead)


def run(config: AppConfig, host: str = "127.0.0.1", port: int = 8000) -> None:
    app = make_app(config)
    uvicorn.run(app, host=host, port=port, log_level="info")
