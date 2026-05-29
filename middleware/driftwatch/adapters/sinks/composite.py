"""Fans a change out to several sinks in sequence."""
from __future__ import annotations

from typing import Iterable, List

from ...application.ports import ChangeSink
from ...domain.change_event import ChangeEvent


class CompositeSink(ChangeSink):
    def __init__(self, sinks: Iterable[ChangeSink]) -> None:
        self._sinks: List[ChangeSink] = list(sinks)

    async def emit(self, event: ChangeEvent) -> None:
        for sink in self._sinks:
            await sink.emit(event)

    async def flush(self) -> None:
        for sink in self._sinks:
            await sink.flush()

    async def aclose(self) -> None:
        for sink in self._sinks:
            await sink.aclose()
