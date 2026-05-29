"""Prints each change to stdout."""
from __future__ import annotations

from ...application.ports import ChangeSink
from ...domain.change_event import ChangeEvent


class ConsoleSink(ChangeSink):
    async def emit(self, event: ChangeEvent) -> None:
        print(str(event), flush=True)
