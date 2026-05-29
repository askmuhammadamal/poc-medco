"""CLI entrypoint: `python -m driftwatch [--mode scan|discover] [flags]`."""
from __future__ import annotations

import argparse
import logging

from .infrastructure.config_loader import load_config
from .infrastructure.service import run


def _parse_args():
    p = argparse.ArgumentParser(prog="driftwatch", description="Modbus scan/discover service + dashboard.")
    p.add_argument("--config", help="Path to a YAML config file (optional).")
    p.add_argument("--mode", choices=["scan", "discover", "Scan", "Discover"], help="Operating mode.")
    p.add_argument("--transport", choices=["tcp", "rtu", "Tcp", "Rtu"], help="Transport.")
    p.add_argument("--host", help="TCP host.")
    p.add_argument("--port", type=int, help="TCP port (PLC).")
    p.add_argument("--rtu-port", dest="rtu_port", help="RTU serial port / COM.")
    p.add_argument("--baud", type=int, help="RTU baud rate.")
    p.add_argument("--unit", type=int, help="Default unit id.")
    p.add_argument("--allow-writes", dest="allow_writes", action="store_true", help="Enable writes (DANGER).")
    p.add_argument("--discovery-end", dest="discovery_end", type=int, help="Discovery end address.")
    p.add_argument("--scan-slaves", dest="scan_slaves", action="store_true", help="Sweep slave ids in discovery.")
    p.add_argument("--http-host", default="127.0.0.1", help="Dashboard bind host (default 127.0.0.1).")
    p.add_argument("--http-port", type=int, default=8000, help="Dashboard port (default 8000).")
    return p.parse_args()


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)-7s %(name)s %(message)s", level=logging.INFO)
    args = _parse_args()
    cli = {
        "mode": args.mode, "transport": args.transport, "host": args.host, "port": args.port,
        "rtu_port": args.rtu_port, "baud": args.baud, "unit": args.unit,
        "allow_writes": True if args.allow_writes else None,
        "discovery_end": args.discovery_end,
        "scan_slaves": True if args.scan_slaves else None,
    }
    config = load_config(args.config, cli)
    run(config, host=args.http_host, port=args.http_port)


if __name__ == "__main__":
    main()
