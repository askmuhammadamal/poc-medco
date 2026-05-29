# Running guide — Driftwatch (Python Modbus monorepo)

Build, run, and test everything. Single language: **Python**. Two parts — the simulator (test PLC)
and the middleware+dashboard (one FastAPI service).

```
Browser ──▶ middleware service (FastAPI, :8000) ──▶ PLC / simulator (:5020)
              scanner loop + dashboard UI + API
```

## 0. Quick start — one script

**Windows:** double-click **`start-windows.bat`**. First run installs Python (via winget) + deps;
then it asks for a PLC (press Enter to use the built-in simulator), starts everything, and opens
the dashboard at http://127.0.0.1:8000.

**macOS / Linux:** one command —
```bash
./start.sh                                 # bundled simulator + dashboard
PLC_HOST=192.168.1.50 ./start.sh           # real PLC over TCP (PLC_PORT default 502)
ALLOW_WRITES=1 ./start.sh                   # enable writes (DANGER: reaches hardware)
```
First run creates the venvs + installs deps automatically. Ctrl-C stops everything it started.

Everything below is the manual / step-by-step path (and how the pieces work).

---

## How to use the dashboard

Open **http://127.0.0.1:8000**. Panels:
- **Live values** — latest value per address (modicon · type · address · label · value · age),
  updating in real time via SSE. Bits show true/false.
- **Change history** — rolling log of every change as it happens.
- **Discovery report** — appears after a `--mode discover` run; shows alive/dead addresses per unit.
- **Write** — set a Coil or HoldingRegister. **Greyed out unless writes are enabled** (start with
  `--allow-writes` / `ALLOW_WRITES=1` / answer "y" in `start-windows.bat`). Requires ticking the
  per-write confirm box. Writes go to **real hardware** — off by default on purpose.

---

## Step-by-step: plug in the I/O → read → write

End-to-end path for the manual route. Pick **one** I/O target in step B.

**A. Prereqs.** Python 3.9+. Two terminals. RTU on macOS needs `socat`.

**B. Plug in the I/O — pick one target.**

- **Simulator (no hardware):** nothing to wire. Run the sim (§2); it listens on `127.0.0.1:5020`.
- **Real PLC over TCP / RJ45:** connect the PLC to the LAN (or direct Ethernet). Note its **IP**,
  **port** (usually `502`), **unit id**. Verify reach: `ping <PLC_IP>` and `nc -vz <PLC_IP> 502`.
- **Real PLC over RTU (USB / RS-485):** plug the USB-serial adapter. Find the port —
  Linux `/dev/ttyUSB0` (`dmesg | tail`), macOS `/dev/tty.usbserial-*`, Windows `COM3`. Match the
  device **baud / parity / unit id**. On Linux add your user to the `dialout` group for serial access.

**C. Start the middleware** matching the target (§3):
```bash
.venv/bin/python -m driftwatch --mode scan                                          # simulator
.venv/bin/python -m driftwatch --mode scan --host 192.168.1.50 --port 502 --unit 1  # TCP/RJ45
.venv/bin/python -m driftwatch --mode scan --transport rtu --rtu-port /dev/ttyUSB0 --baud 9600 --unit 1  # RTU
```
Unknown addresses on a real device? Map first: `--mode discover --discovery-end 1000 --scan-slaves`.

**D. Read.** Per cycle the scanner polls each range → `client.read(...)` through the decorator stack
(`SafetyGuard → Resilient → Tcp/Rtu → pymodbus`) → socket/serial I/O → compares vs cache → emits a
`ChangeEvent` to the sinks on change. Illegal-address (`0x02`) → bisect & mark dead, keep polling.
See the reads via the dashboard "Live values" grid, `curl :8000/api/state`, `curl -N :8000/api/stream`,
or `logs/changes-YYYY-MM-DD.csv`.

**E. Write** (only Coil / HoldingRegister; OFF by default — 3 gates: dashboard greys panel · API
403 · `SafetyGuard` raises `WriteBlockedError`). Restart with `--allow-writes`, then:
```bash
curl -X POST :8000/api/write -H 'Content-Type: application/json' \
  -d '{"objectType":"HoldingRegister","address":100,"value":4321,"confirm":true,"unitId":1}'
```
Or use the dashboard "Write" panel (tick the per-write confirm box). API validates writable type +
`confirm` + `allowWrites`; SafetyGuard re-checks; the wire write fires. The next poll re-reads the
address and the new value shows in `/api/stream`, the dashboard, and the CSV.

> ⚠️ Real PLC writes change physical outputs/setpoints. Verify address + value before sending; keep
> `--allow-writes` off whenever you're only observing.

---

## 1. Prerequisites

- **Python 3.9+** (`python3 --version`). That's the only toolchain needed.
- macOS/Linux/Windows. RTU on macOS needs `socat` (Homebrew) for a virtual serial pair.

## 2. Simulator (the test PLC)

```bash
cd plc-simulator
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # pymodbus 3.7.4
.venv/bin/python plc_sim.py --mode known           # listens 0.0.0.0:5020, ticks every 1s
```
Modes: `--mode known` (seeded demo) · `--mode blank` (zero-filled) · `--mode map --map-file
register_map.example.yaml`. Chaos: `--chaos delay=50-500,error=0.02`.

`known` seeds: HR100=1234, HR101=heartbeat, HR102=temp, IR0=50, IR10=random, coils/DI at 0 & 10/20.

## 3. Middleware + dashboard (one service)

In a second terminal:

```bash
cd middleware
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m driftwatch --mode scan
```
Opens **http://127.0.0.1:8000** — live value grid, change history, discovery viewer, write panel.
Connects to the sim on `127.0.0.1:5020`, polls 4 ranges, prints changes, writes
`logs/changes-YYYY-MM-DD.csv`.

### Real PLC over TCP
```bash
.venv/bin/python -m driftwatch --mode scan --host 192.168.1.50 --port 502 --unit 1
```
### Real PLC over RTU (serial / RS-485)
```bash
.venv/bin/python -m driftwatch --mode scan --transport rtu --rtu-port /dev/ttyUSB0 --baud 9600
```
### Enable writes (DANGER — reaches real hardware)
```bash
.venv/bin/python -m driftwatch --mode scan --allow-writes
```
Blocked by default → `POST /api/write` returns 403 and the dashboard write panel is greyed out.

### Discovery (find what's actually there)
```bash
.venv/bin/python -m driftwatch --mode discover --discovery-end 1000 --scan-slaves
```
Writes `logs/discovery-YYYYMMDD-HHMMSS.jsonl`; the dashboard's discovery viewer renders the newest.

### Config file
Built-in defaults already define the 4 demo ranges + console/CSV sinks. To customize, copy
`config.example.yaml` → `config.yaml` and run with `--config config.yaml`. Precedence:
defaults → YAML → `DW_*` env → CLI flags.

## 4. API endpoints (served by the same service)

| Path | Purpose |
|------|---------|
| `GET /` | dashboard UI |
| `GET /api/state` | snapshot: latest value per address |
| `GET /api/stream` | SSE live change events |
| `GET /api/config` | transport, ranges, `allowWrites` |
| `GET /api/health` | connection state, last scan, `allowWrites` |
| `GET /api/discovery` | parsed discovery report (204 if none yet) |
| `POST /api/write` | write a Coil/HoldingRegister (gated; 403 when disabled) |

## 5. Tests

```bash
cd middleware
.venv/bin/pytest                       # full suite (59), in-memory fake client — no sockets
.venv/bin/pytest tests/test_scanner.py
.venv/bin/pytest -k illegal_address
```

## 6. End-to-end check

1. `plc-simulator`: `.venv/bin/python plc_sim.py --mode known` (:5020).
2. `middleware`: `.venv/bin/python -m driftwatch --mode scan --allow-writes` (:8000).
3. `curl :8000/api/state`, `curl -N :8000/api/stream`, open `http://127.0.0.1:8000`.
4. Write blocked check: omit `--allow-writes` → `POST /api/write` returns **403**.
   With `--allow-writes` → **200**; the new value appears in `/api/stream` and the CSV.

## 7. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Port 5020 in use | another simulator running — one at a time. |
| Port 8000 in use | `--http-port 8001`. |
| `pymodbus` mismatch | keep sim + middleware both on `pymodbus==3.7.4`. |
| RTU on macOS | `brew install socat`; make a PTY pair (see `plc-simulator/README.md`). |
| Writes return 403 | by design — pass `--allow-writes` to enable. |
