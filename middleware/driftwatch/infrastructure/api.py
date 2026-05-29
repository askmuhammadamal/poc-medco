"""FastAPI surface for the dashboard. Same JSON contract as before so the static/ UI works
unchanged. Read endpoints expose live scanner state; the single write endpoint is gated by the
safety guard."""
from __future__ import annotations

import asyncio
import glob
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..application.options import AppConfig
from ..application.scanner import ScannerService
from ..adapters.sinks.live import LiveStateSink
from ..adapters.transport.safety import WriteBlockedError
from ..domain.change_event import ChangeEvent
from ..domain.exceptions import ModbusProtocolException, ModbusTransportException
from ..domain.modicon import ModiconAddress
from ..domain.object_type import ModbusObjectType

log = logging.getLogger("driftwatch.api")


@dataclass
class AppState:
    live: LiveStateSink
    client: object                 # the SafetyGuard-wrapped pipeline
    config: AppConfig
    scanner: Optional[ScannerService] = None


def _dto(evt: ChangeEvent) -> dict:
    return {
        "timestamp": evt.timestamp.isoformat(),
        "unitId": evt.unit_id,
        "objectType": evt.object_type.value,
        "address": evt.address,
        "modicon": evt.modicon,
        "oldValue": evt.old_value,
        "newValue": evt.new_value,
        "isBit": evt.object_type.is_bit,
        "label": evt.label,
    }


def create_app(state: AppState, static_dir: Path, lifespan=None) -> FastAPI:
    app = FastAPI(title="Modbus Middleware", lifespan=lifespan)
    app.state.ctx = state

    @app.get("/api/state")
    async def get_state():
        return [_dto(e) for e in state.live.snapshot()]

    @app.get("/api/health")
    async def get_health():
        scan = state.scanner.last_successful_scan if state.scanner else None
        return {
            "connectionState": state.client.state.value,
            "lastSuccessfulScan": scan.isoformat() if scan else None,
            "allowWrites": state.config.modbus.safety.allow_writes,
        }

    @app.get("/api/config")
    async def get_config():
        m = state.config.modbus
        return {
            "mode": state.config.mode,
            "transport": m.transport,
            "tcp": {"host": m.tcp.host, "port": m.tcp.port},
            "rtu": {"portName": m.rtu.port_name, "baudRate": m.rtu.baud_rate},
            "unitId": m.unit_id,
            "allowWrites": m.safety.allow_writes,
            "ranges": [
                {"objectType": r.object_type.value, "start": r.start, "count": r.count,
                 "pollMs": r.poll_ms, "unitId": r.unit_id, "label": r.label}
                for r in state.config.scanner.ranges
            ],
        }

    @app.get("/api/discovery")
    async def get_discovery():
        report_path = state.config.discovery.report_path
        rooted = report_path if os.path.isabs(report_path) else os.path.join(os.getcwd(), report_path)
        directory = os.path.dirname(rooted)
        stem, ext = os.path.splitext(os.path.basename(rooted))
        candidates = sorted(glob.glob(os.path.join(directory, f"{stem}-*{ext}")), key=os.path.getmtime, reverse=True)
        if not candidates and os.path.exists(rooted):
            candidates = [rooted]
        if not candidates:
            return Response(status_code=204)
        summary = None
        object_types = []
        with open(candidates[0], "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("kind") == "summary":
                    summary = obj
                else:
                    object_types.append(obj)
        return {"summary": summary, "objectTypes": object_types}

    @app.get("/api/stream")
    async def get_stream(request: Request):
        async def gen():
            sub_id, queue = state.live.subscribe()
            try:
                for evt in state.live.snapshot():
                    yield f"data: {json.dumps(_dto(evt))}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        evt = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield f"data: {json.dumps(_dto(evt))}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                state.live.unsubscribe(sub_id)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/write")
    async def post_write(request: Request):
        body = await request.json()
        if not body.get("confirm"):
            return JSONResponse({"error": "confirm must be true to issue a write."}, status_code=400)
        try:
            otype = ModbusObjectType.parse(str(body.get("objectType", "")))
        except ValueError:
            return JSONResponse({"error": f"Unknown objectType {body.get('objectType')!r}."}, status_code=400)
        if not otype.is_writable:
            return JSONResponse({"error": f"{otype.value} is read-only. Writable: Coil, HoldingRegister."},
                                status_code=400)
        if not state.config.modbus.safety.allow_writes:
            log.warning("Write blocked (AllowWrites=false): %s unit=%s addr=%s",
                        otype.value, body.get("unitId"), body.get("address"))
            return JSONResponse(
                {"error": "Writes are disabled.", "allowWrites": False,
                 "hint": "Start the service with --allow-writes (Modbus.Safety.AllowWrites)."},
                status_code=403)

        unit = int(body["unitId"])
        address = int(body["address"])
        value = int(body["value"])
        try:
            if otype is ModbusObjectType.COIL:
                await state.client.write_single_coil(unit, address, value != 0)
            else:
                if value < 0 or value > 0xFFFF:
                    return JSONResponse({"error": f"value {value} out of range for a 16-bit register."},
                                        status_code=400)
                await state.client.write_single_register(unit, address, value)
            modicon = ModiconAddress.from_protocol(otype, address).to_modicon_string()
            log.info("Write OK: %s %s unit=%s addr=%s value=%s", otype.value, modicon, unit, address, value)
            return {"ok": True, "modicon": modicon}
        except WriteBlockedError as exc:
            return JSONResponse({"error": str(exc), "allowWrites": False}, status_code=403)
        except ModbusProtocolException as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
        except ModbusTransportException as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)

    @app.get("/")
    async def index():
        return FileResponse(static_dir / "index.html")

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app
