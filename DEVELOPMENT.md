# Driftwatch — development guide

Architecture and commands for working in this repository (project name **Driftwatch**; the GitHub
repo slug is `plc-poc`).

## Repository shape

Single-language (Python) monorepo. Two parts:

- **`plc-simulator/`** — Python Modbus **server** simulator (`pymodbus`). The test PLC. TCP + RTU,
  all 4 object types, YAML register maps, chaos injection.
- **`middleware/`** — Python Modbus **client** middleware + dashboard, as ONE FastAPI service.
  Scanner/discovery client + dashboard + API in one process.

Git repo (remote `git@github.com:askmuhammadamal/plc-poc.git`).

## Commands

### Simulator (the test PLC)
```bash
cd plc-simulator
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python plc_sim.py --mode known      # seeded demo, ticks every 1s, listens 0.0.0.0:5020
.venv/bin/python plc_sim.py --mode map --map-file register_map.example.yaml
.venv/bin/python plc_sim.py --mode known --chaos delay=50-500,error=0.02
```

### Middleware + dashboard (one service)
```bash
cd middleware
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m driftwatch --mode scan                 # serves UI+API on http://127.0.0.1:8000
.venv/bin/python -m driftwatch --mode scan --allow-writes  # enable the write panel (DANGER)
.venv/bin/python -m driftwatch --mode discover --discovery-end 1000 --scan-slaves
.venv/bin/python -m driftwatch --config config.yaml        # explicit config file
```
CLI flags: `--mode --transport --host --port --rtu-port --baud --unit --allow-writes
--discovery-end --scan-slaves --http-host --http-port`. Config precedence: built-in defaults →
`config.yaml` (`--config`) → `DW_*` env → CLI flags. See `config.example.yaml`.

### Tests
```bash
cd middleware
.venv/bin/pytest                                  # full suite (59)
.venv/bin/pytest tests/test_scanner.py            # one file
.venv/bin/pytest -k illegal_address               # by name
```
`pyproject.toml` sets `asyncio_mode = auto` (pytest-asyncio). Tests use an in-memory
`tests/fake_client.py` — no sockets, deterministic.

## Architecture (`middleware/driftwatch/`) — Clean Architecture layers

Four packages, dependencies point **inward only** (enforceable by grep; see Gotchas):

```
domain/          entities + value objects, ZERO internal/framework deps
  object_type, connection_state, exceptions, modicon, decoder, change_event
application/     use cases + PORTS + option value-objects; imports domain only
  ports (ModbusClient, ChangeSink), options, scan_range, dead_tracker,
  scanner, slave_scanner, discovery, discovery_report
adapters/        port implementations; imports application + domain
  transport/{pymodbus_base,tcp,rtu,resilient,safety,delegating}
  sinks/{console,csv_sink,live,composite}, discovery_report_writer
infrastructure/  frameworks + composition root; imports any inward layer
  api (FastAPI), config_loader, service (build pipeline + lifespan + uvicorn)
__main__.py      CLI → infrastructure.service.run
```
The dependency rule is the point: the `ModbusClient`/`ChangeSink` **ports** live in
`application/ports.py`; concrete pymodbus/FastAPI/CSV code lives only in `adapters/` +
`infrastructure/`. Domain and application are framework-free and unit-tested with a fake adapter.

**One FastAPI service, one asyncio loop.** `infrastructure/service.py` builds the client pipeline +
sinks + scanner, then `make_app()` returns a FastAPI app whose **lifespan** connects the client and
launches the work: one scanner task per range (`--mode scan`) or a one-shot discovery that writes a
report (`--mode discover`). The same app serves the dashboard UI + API on a single port (8000).

**Two operating modes** (`mode` config / `--mode`):
- **Scan** — `application/scanner.py` polls configured ranges, caches values, emits a `ChangeEvent`
  on change. One `asyncio.Task` per range.
- **Discover** — `application/discovery.py` sweeps all 4 object types over an address range
  (optionally probing unit IDs first via `application/slave_scanner.py`); the report is written by
  `adapters/discovery_report_writer.py` as JSON Lines.

**Transport decorator pipeline** (`adapters/transport/`, built in `service.build_client`, outermost
first): `SafetyGuardModbusClient` → `ResilientModbusClient` → concrete `TcpModbusClient`/
`RtuModbusClient` (wrap pymodbus via `pymodbus_base.py`). All implement the `ModbusClient` port
(`application/ports.py`). `delegating.py` is the forwarding base for the decorators.

**Key invariants** (tests enforce; preserve):
- **Writes blocked by default.** `SafetyGuardModbusClient` raises `WriteBlockedError` unless
  `Modbus.Safety.allow_writes`. Scanner/discovery never write. `POST /api/write` also requires a
  `confirm` flag, validates writable type (Coil/HoldingRegister), and returns 403 when disabled.
- **Protocol exception ≠ transport exception.** `pymodbus_base` maps an `ExceptionResponse`
  (`exception_code`; `0x02` → `is_address_invalid`) to `ModbusProtocolException` (connection stays
  healthy); `ConnectionException`/`ModbusIOException`/timeout → `ModbusTransportException` + state
  `Faulted`. `ResilientModbusClient` reconnects with exponential backoff + retries once on transport
  faults; protocol exceptions pass through untouched.
- **Dead-address tracker keyed per `(unit, object_type, address)`** (`application/dead_tracker.py`).
  On `ILLEGAL_DATA_ADDRESS` the scanner/discovery **bisect** to the exact dead address(es) instead
  of dropping the batch, then skip them via `live_sub_ranges()`.
- **`LiveStateSink.emit` must never block or throw** — it runs inside the scanner poll loop. Each
  SSE subscriber has a bounded `asyncio.Queue(1024)` with drop-oldest. Snapshot gives authoritative
  state on reconnect.

**Sinks** (`adapters/sinks/`, composed in `service.build_sink`): `ConsoleSink`, `CsvSink`
(daily-rotated `logs/changes-YYYY-MM-DD.csv`, columns `timestamp,unit_id,object_type,address,
modicon,old_value,new_value,label`), `LiveStateSink` (always on; powers `/api/state` +
`/api/stream`), `CompositeSink`. All implement the `ChangeSink` port (`application/ports.py`).

**API contract** (`infrastructure/api.py`) — camelCase JSON consumed by `static/app.js`:
`GET /api/{state,stream(SSE),discovery,config,health}`, `POST /api/write`. Discovery reports are
timestamped (`{stem}-yyyymmdd-HHMMSS.jsonl`); `/api/discovery` returns the newest match.

**Address model**: `domain/modicon.py` (40101↔HR 100, 30001↔IR 0). `domain/decoder.py` decodes
int16/uint16/int32/uint32/float32/int64/float64/ascii across 4 word orders (ABCD/CDAB/BADC/DCBA).

## Gotchas
- **Python 3.9**: `asyncio.Lock()` binds to the loop at construction, so `pymodbus_base` creates its
  lock lazily inside the running loop. Don't move it back into `__init__`.
- Pin `pymodbus==3.7.4` to match the simulator. The async client uses `slave=`/`count=` kwargs and
  `resp.isError()` / `resp.exception_code`.
- RTU on macOS needs a `socat` virtual serial pair (see `plc-simulator/README.md`).

## Out of scope (don't add without asking)
No TLS / Modbus Security, no historian/time-series ingestion (CSV is the bridge), no automatic
writes during discovery, no auth on the dashboard (loopback-only by default — bind non-loopback only
behind your own auth).
