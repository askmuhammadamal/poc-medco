"""Appends change events to a CSV with optional daily rotation.

Columns (identical to the .NET build so existing tooling/imports keep working):
  timestamp,unit_id,object_type,address,modicon,old_value,new_value,label
"""
from __future__ import annotations

import asyncio
import csv
import os
from datetime import date

from ...application.options import CsvSinkOptions
from ...application.ports import ChangeSink
from ...domain.change_event import ChangeEvent

HEADER = ["timestamp", "unit_id", "object_type", "address", "modicon", "old_value", "new_value", "label"]


class CsvSink(ChangeSink):
    def __init__(self, options: CsvSinkOptions) -> None:
        self._opts = options
        self._file = None
        self._writer = None
        self._current_day: date | None = None
        self._since_flush = 0
        self._lock = asyncio.Lock()

    def _path_for(self, day: date) -> str:
        if self._opts.rotate_daily:
            name = f"{self._opts.file_prefix}-{day.isoformat()}.csv"
        else:
            name = f"{self._opts.file_prefix}.csv"
        return os.path.join(self._opts.directory, name)

    def _ensure_file(self, day: date) -> None:
        if self._file is not None and self._current_day == day:
            return
        if self._file is not None:
            self._file.close()
        os.makedirs(self._opts.directory, exist_ok=True)
        path = self._path_for(day)
        new = not os.path.exists(path) or os.path.getsize(path) == 0
        self._file = open(path, "a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        if new:
            self._writer.writerow(HEADER)
        self._current_day = day

    async def emit(self, event: ChangeEvent) -> None:
        async with self._lock:
            self._ensure_file(event.timestamp.date())
            self._writer.writerow([
                event.timestamp.isoformat(),
                event.unit_id,
                event.object_type.value,
                event.address,
                event.modicon,
                "" if event.old_value is None else event.old_value,
                event.new_value,
                event.label or "",
            ])
            self._since_flush += 1
            if self._since_flush >= max(1, self._opts.flush_every):
                self._file.flush()
                self._since_flush = 0

    async def flush(self) -> None:
        async with self._lock:
            if self._file is not None:
                self._file.flush()
                self._since_flush = 0

    async def aclose(self) -> None:
        async with self._lock:
            if self._file is not None:
                self._file.flush()
                self._file.close()
                self._file = None
