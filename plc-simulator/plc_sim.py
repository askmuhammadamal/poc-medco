"""Modbus PLC simulator (TCP + RTU) with all four object types, address gaps, and chaos injection.

Modes:
  --mode known         Pre-populate HR/IR/Coils/DI with deterministic patterns + live ticker.
  --mode blank         All four object types allocated but zero-filled (no ticker).
  --mode map           Load a vendor-style YAML map; unallocated addresses raise ILLEGAL_DATA_ADDRESS.

Transports:
  --transport tcp      Default. Listens on host:tcp-port (default 0.0.0.0:5020).
  --transport rtu      Opens a serial port (use socat on macOS to make a virtual COM pair).

Chaos (all transports):
  --chaos delay=50-500,error=0.02
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
    ModbusSparseDataBlock,
)
from pymodbus.server import StartAsyncSerialServer, StartAsyncTcpServer

from chaos import ChaosSlaveContext, parse_spec

logging.basicConfig(format="%(asctime)s %(levelname)-7s %(name)s %(message)s", level=logging.INFO)
log = logging.getLogger("plc_sim")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_TCP_PORT = 5020
DEFAULT_REGISTER_SPAN = 1000  # holding + input register address space size in known/blank modes

# Known-mode register layout.
ADDR_STATIC_ID = 100
ADDR_HEARTBEAT = 101
ADDR_TEMPERATURE = 102
STATIC_ID = 1234


@dataclass
class LiveRule:
    """Per-address dynamic behaviour: heartbeat counter or random within bounds."""

    address: int
    mode: str  # "heartbeat" | "random"
    min: int = 0
    max: int = 0xFFFF
    state: int = 0


@dataclass
class SlaveSpec:
    """Static + dynamic content for one Modbus unit ID."""

    unit_id: int
    holding: dict[int, int] = field(default_factory=dict)
    inputs: dict[int, int] = field(default_factory=dict)
    coils: dict[int, bool] = field(default_factory=dict)
    discrete: dict[int, bool] = field(default_factory=dict)
    live_holding: list[LiveRule] = field(default_factory=list)
    live_inputs: list[LiveRule] = field(default_factory=list)


def _encode_value(reg_type: str, value: Any, word_order: str, length_bytes: int) -> list[int]:
    """Encode a typed value into a list of 16-bit registers using the given word order."""
    if reg_type == "uint16":
        return [int(value) & 0xFFFF]
    if reg_type == "int16":
        packed = struct.pack(">h", int(value))
        return [int.from_bytes(packed, "big")]

    if reg_type in ("int32", "uint32", "float32"):
        if reg_type == "int32":
            raw = struct.pack(">i", int(value))
        elif reg_type == "uint32":
            raw = struct.pack(">I", int(value))
        else:
            raw = struct.pack(">f", float(value))
        return _apply_word_order(raw, word_order)

    if reg_type == "string":
        text = str(value).encode("ascii", errors="replace")
        if length_bytes <= 0:
            length_bytes = len(text) + (len(text) % 2)
        text = text.ljust(length_bytes, b"\x00")[:length_bytes]
        regs: list[int] = []
        for i in range(0, length_bytes, 2):
            regs.append(int.from_bytes(text[i:i + 2], "big"))
        return regs

    raise ValueError(f"Unsupported register type: {reg_type}")


def _apply_word_order(raw: bytes, order: str) -> list[int]:
    """Reorder a 4-byte payload into two registers per Modbus word-order conventions."""
    if len(raw) != 4:
        raise ValueError("word-order helper expects exactly 4 bytes")
    a, b, c, d = raw[0], raw[1], raw[2], raw[3]
    order = order.upper()
    if order == "ABCD":
        bytes_ordered = (a, b, c, d)
    elif order == "CDAB":
        bytes_ordered = (c, d, a, b)
    elif order == "BADC":
        bytes_ordered = (b, a, d, c)
    elif order == "DCBA":
        bytes_ordered = (d, c, b, a)
    else:
        raise ValueError(f"Unknown word order: {order}")
    high = (bytes_ordered[0] << 8) | bytes_ordered[1]
    low = (bytes_ordered[2] << 8) | bytes_ordered[3]
    return [high, low]


def build_known_spec() -> SlaveSpec:
    spec = SlaveSpec(unit_id=1)
    # Holding registers
    spec.holding = {addr: 0 for addr in range(DEFAULT_REGISTER_SPAN)}
    spec.holding[ADDR_STATIC_ID] = STATIC_ID
    spec.holding[ADDR_HEARTBEAT] = 0
    spec.holding[ADDR_TEMPERATURE] = 250
    # Pack a float32 (1.0) at 200-201 in CDAB order so middleware decoder tests can target it.
    for offset, reg in enumerate(_apply_word_order(struct.pack(">f", 1.0), "CDAB")):
        spec.holding[200 + offset] = reg
    spec.live_holding = [
        LiveRule(ADDR_HEARTBEAT, "heartbeat"),
        LiveRule(ADDR_TEMPERATURE, "random", min=200, max=350),
    ]
    # Input registers
    spec.inputs = {addr: 0 for addr in range(DEFAULT_REGISTER_SPAN)}
    spec.inputs[0] = 50
    spec.live_inputs = [LiveRule(10, "random", min=0, max=100)]
    # Coils + discrete inputs
    spec.coils = {addr: False for addr in range(256)}
    spec.coils[0] = True
    spec.coils[10] = True
    spec.discrete = {addr: False for addr in range(256)}
    spec.discrete[0] = True
    spec.discrete[20] = True
    return spec


def build_blank_spec() -> SlaveSpec:
    spec = SlaveSpec(unit_id=1)
    spec.holding = {addr: 0 for addr in range(DEFAULT_REGISTER_SPAN)}
    spec.inputs = {addr: 0 for addr in range(DEFAULT_REGISTER_SPAN)}
    spec.coils = {addr: False for addr in range(256)}
    spec.discrete = {addr: False for addr in range(256)}
    return spec


def build_map_spec(path: Path) -> SlaveSpec:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Map file {path} must contain a YAML mapping")

    spec = SlaveSpec(unit_id=int(raw.get("unit_id", 1)))

    def _populate_registers(entries: dict[Any, Any], live: list[LiveRule]) -> dict[int, int]:
        out: dict[int, int] = {}
        if not entries:
            return out
        for addr_raw, entry in entries.items():
            addr = int(addr_raw)
            if not isinstance(entry, dict):
                out[addr] = int(entry) & 0xFFFF
                continue
            reg_type = entry.get("type", "uint16")
            word_order = entry.get("word_order", "ABCD")
            length_bytes = int(entry.get("length", 0))
            mode = entry.get("mode")
            if mode in ("heartbeat", "random"):
                out[addr] = int(entry.get("value", 0))
                live.append(LiveRule(
                    address=addr,
                    mode=mode,
                    min=int(entry.get("min", 0)),
                    max=int(entry.get("max", 0xFFFF)),
                ))
                continue
            encoded = _encode_value(reg_type, entry.get("value", 0), word_order, length_bytes)
            for i, reg in enumerate(encoded):
                out[addr + i] = reg
        return out

    spec.holding = _populate_registers(raw.get("holding_registers") or {}, spec.live_holding)
    spec.inputs = _populate_registers(raw.get("input_registers") or {}, spec.live_inputs)

    for addr, val in (raw.get("coils") or {}).items():
        spec.coils[int(addr)] = bool(val)
    for addr, val in (raw.get("discrete_inputs") or {}).items():
        spec.discrete[int(addr)] = bool(val)
    return spec


def _sparse_block(values: dict[int, int]) -> ModbusSparseDataBlock | ModbusSequentialDataBlock:
    """Build a datastore that responds with ILLEGAL_DATA_ADDRESS for absent keys."""
    if not values:
        # Empty dict still needs a block so reads return error rather than crash.
        return ModbusSparseDataBlock({0: 0})
    return ModbusSparseDataBlock(values)


def _build_context(spec: SlaveSpec, chaos_text: str | None) -> tuple[ModbusServerContext, ModbusSlaveContext]:
    holding_block = _sparse_block(spec.holding)
    input_block = _sparse_block(spec.inputs)
    coil_block = ModbusSparseDataBlock({a: (1 if v else 0) for a, v in spec.coils.items()} or {0: 0})
    discrete_block = ModbusSparseDataBlock({a: (1 if v else 0) for a, v in spec.discrete.items()} or {0: 0})

    slave = ModbusSlaveContext(
        di=discrete_block,
        co=coil_block,
        ir=input_block,
        hr=holding_block,
        zero_mode=True,
    )
    chaos_spec = parse_spec(chaos_text)
    if chaos_spec.enabled:
        slave = ChaosSlaveContext(slave, chaos_spec)
        log.info(
            "Chaos enabled: delay=%d-%dms error_rate=%.3f",
            chaos_spec.delay_min_ms, chaos_spec.delay_max_ms, chaos_spec.error_rate,
        )

    server_context = ModbusServerContext(slaves={spec.unit_id: slave}, single=False)
    return server_context, slave


async def _ticker(slave: ModbusSlaveContext, rules_holding: list[LiveRule], rules_inputs: list[LiveRule]) -> None:
    """Advance heartbeats and random values once per second."""
    if not rules_holding and not rules_inputs:
        return
    while True:
        await asyncio.sleep(1.0)
        _advance_rules(slave, 3, rules_holding)   # FC03 = holding registers
        _advance_rules(slave, 4, rules_inputs)    # FC04 = input registers


def _advance_rules(slave: ModbusSlaveContext, function_code: int, rules: list[LiveRule]) -> None:
    for rule in rules:
        if rule.mode == "heartbeat":
            rule.state = (rule.state + 1) & 0xFFFF
            slave.setValues(function_code, rule.address, [rule.state])
        elif rule.mode == "random":
            value = random.randint(rule.min, rule.max)
            slave.setValues(function_code, rule.address, [value])


async def _run_tcp(spec: SlaveSpec, host: str, port: int, chaos: str | None) -> None:
    context, slave = _build_context(spec, chaos)
    log.info("Starting Modbus TCP server on %s:%d (unit %d)", host, port, spec.unit_id)
    asyncio.create_task(_ticker(slave, spec.live_holding, spec.live_inputs))
    await StartAsyncTcpServer(context=context, address=(host, port))


async def _run_rtu(spec: SlaveSpec, port: str, baud: int, parity: str, data_bits: int, stop_bits: int,
                   chaos: str | None) -> None:
    context, slave = _build_context(spec, chaos)
    log.info(
        "Starting Modbus RTU server on %s @ %d %d%s%d (unit %d)",
        port, baud, data_bits, parity, stop_bits, spec.unit_id,
    )
    asyncio.create_task(_ticker(slave, spec.live_holding, spec.live_inputs))
    await StartAsyncSerialServer(
        context=context,
        port=port,
        baudrate=baud,
        bytesize=data_bits,
        parity=parity,
        stopbits=stop_bits,
        framer="rtu",
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Modbus PLC simulator")
    p.add_argument("--mode", choices=["known", "blank", "map"], default="known")
    p.add_argument("--map-file", type=Path, help="YAML register map (required for --mode map)")
    p.add_argument("--transport", choices=["tcp", "rtu"], default="tcp")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT)
    p.add_argument("--rtu-port", default="/tmp/ttyV0")
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--parity", choices=["N", "E", "O"], default="N")
    p.add_argument("--data-bits", type=int, default=8)
    p.add_argument("--stop-bits", type=int, default=1)
    p.add_argument("--chaos", default=None, help="e.g. 'delay=50-500,error=0.02'")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.getLogger().setLevel(args.log_level.upper())

    if args.mode == "known":
        spec = build_known_spec()
    elif args.mode == "blank":
        spec = build_blank_spec()
    else:
        if args.map_file is None:
            print("ERROR: --map-file is required when --mode map", file=sys.stderr)
            sys.exit(2)
        spec = build_map_spec(args.map_file)

    if args.transport == "tcp":
        asyncio.run(_run_tcp(spec, args.host, args.tcp_port, args.chaos))
    else:
        asyncio.run(_run_rtu(
            spec, args.rtu_port, args.baud, args.parity, args.data_bits, args.stop_bits, args.chaos,
        ))


if __name__ == "__main__":
    main()
