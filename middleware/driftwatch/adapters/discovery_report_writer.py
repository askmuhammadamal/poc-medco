"""JSON Lines writer for a DiscoveryReport.

Timestamps the filename ({stem}-yyyymmdd-HHMMSS{ext}) in the directory of the configured report
path, and returns the path written. One JSON object per line: a `summary` line, then one
`object_type` line per (unit x object type)."""
from __future__ import annotations

import json
import os
from datetime import datetime

from ..application.discovery_report import DiscoveryReport


def _resolve_output_path(report_path: str, now: datetime) -> str:
    if os.path.isabs(report_path):
        return report_path
    directory = os.path.dirname(report_path)
    stem, ext = os.path.splitext(os.path.basename(report_path))
    stamped = f"{stem}-{now.strftime('%Y%m%d-%H%M%S')}{ext}"
    return os.path.join(directory, stamped)


def write_report(report_path: str, report: DiscoveryReport, now: datetime | None = None) -> str:
    now = now or datetime.utcnow()
    path = _resolve_output_path(report_path, now)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    duration_ms = int(((report.completed_at or report.started_at) - report.started_at).total_seconds() * 1000)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "kind": "summary",
            "startedAt": report.started_at.isoformat(),
            "completedAt": (report.completed_at or report.started_at).isoformat(),
            "respondingUnits": report.responding_units,
            "durationMs": duration_ms,
        }) + "\n")
        for unit in report.units:
            for ot in unit.object_types:
                f.write(json.dumps({
                    "kind": "object_type",
                    "unitId": unit.unit_id,
                    "objectType": ot.object_type.value,
                    "aliveCount": len(ot.alive),
                    "deadCount": len(ot.dead),
                    "errorCount": len(ot.errors),
                    "alive": [{"address": a.address, "modicon": a.modicon, "value": a.value} for a in ot.alive],
                    "dead": [{"start": d.start, "end": d.end} for d in ot.dead],
                    "errors": [{"start": e.start, "end": e.end, "reason": e.reason} for e in ot.errors],
                }) + "\n")
    return path
