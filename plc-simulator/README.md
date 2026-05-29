# PLC Simulator (Python)

Modbus PLC simulator using `pymodbus`. Supports TCP + RTU transport, all four object
types (coils, discrete inputs, input registers, holding registers), vendor-style
register maps loaded from YAML, and runtime chaos injection.

## Setup

```bash
cd plc-simulator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Modes

```bash
# Pre-populated demo (HR, IR, coils, DI seeded; heartbeat + temperature tick every 1s).
python plc_sim.py --mode known

# All four object types allocated but zero-filled, no ticker.
python plc_sim.py --mode blank

# Load a vendor-style YAML map. Unallocated addresses respond with ILLEGAL_DATA_ADDRESS.
python plc_sim.py --mode map --map-file register_map.example.yaml
```

## Known-mode register layout

| Object type      | Address | Behavior                              |
|------------------|---------|---------------------------------------|
| Holding register | 100     | Constant `1234` (static device ID)    |
| Holding register | 101     | Heartbeat: increments every 1s        |
| Holding register | 102     | Random temperature x10 (200..350)     |
| Holding register | 200-201 | Float32 `1.0` in CDAB word order      |
| Input register   | 0       | Constant `50`                         |
| Input register   | 10      | Random 0..100 every 1s                |
| Coil             | 0, 10   | Set true                              |
| Discrete input   | 0, 20   | Set true                              |

Holding + input register space spans addresses 0..999 (zero everywhere else).
Coils + discrete inputs span 0..255.

## RTU transport

Run as an RTU server (multidrop slave) on a serial port. On macOS use `socat` to
create a virtual COM pair so both ends are local:

```bash
socat -d -d pty,raw,echo=0 pty,raw,echo=0
# Output: PTY is /dev/ttys003   PTY is /dev/ttys004
python plc_sim.py --transport rtu --rtu-port /dev/ttys003 --baud 9600

# Point the middleware at /dev/ttys004 in appsettings.json.
```

On Windows, no socat needed — connect the USB-to-RS485 adapter and use `COMx`.

## Chaos injection

Inject realistic problems on top of any mode:

```bash
python plc_sim.py --mode known --chaos delay=50-500,error=0.02
```

- `delay=50-500` — each request is held for a random 50-500 ms.
- `error=0.02` — 2% of requests fail with `SLAVE_DEVICE_FAILURE`.

Use this to validate the middleware's reconnect logic, timeout handling, and
dead-address tracker against a simulated noisy bus.

## YAML map format

```yaml
unit_id: 1
holding_registers:
  100: { type: uint16, value: 1234 }
  101: { type: uint16, mode: heartbeat }
  102: { type: uint16, mode: random, min: 200, max: 350 }
  200: { type: float32, value: 3.14159, word_order: CDAB }
  210: { type: int32,  value: -1000000, word_order: ABCD }
  220: { type: string, value: "PLC-SIM", length: 16 }
input_registers:
  0:  { type: uint16, value: 50 }
coils:
  0:  true
  10: true
discrete_inputs:
  0: true
  20: true
```

Supported types: `uint16`, `int16`, `int32`, `uint32`, `float32`, `string`.
Supported `word_order` values: `ABCD` (big-endian), `CDAB`, `BADC`, `DCBA`.

## Full CLI

```
--mode {known,blank,map}       (default: known)
--map-file PATH                (required for --mode map)
--transport {tcp,rtu}          (default: tcp)
--host HOST                    (default: 0.0.0.0)
--tcp-port N                   (default: 5020)
--rtu-port PATH                (default: /tmp/ttyV0)
--baud N                       (default: 9600)
--parity {N,E,O}               (default: N)
--data-bits N                  (default: 8)
--stop-bits N                  (default: 1)
--chaos SPEC                   (e.g. "delay=50-500,error=0.02")
--log-level LEVEL              (default: INFO)
```
