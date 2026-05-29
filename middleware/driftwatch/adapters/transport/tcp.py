"""TCP transport — wraps pymodbus AsyncModbusTcpClient."""
from __future__ import annotations

import logging

from pymodbus.client import AsyncModbusTcpClient

from ...application.options import ModbusOptions
from .pymodbus_base import PymodbusClientBase

log = logging.getLogger("driftwatch.transport.tcp")


class TcpModbusClient(PymodbusClientBase):
    def __init__(self, options: ModbusOptions) -> None:
        super().__init__()
        self._opts = options.tcp

    async def _open(self) -> bool:
        self._client = AsyncModbusTcpClient(
            host=self._opts.host,
            port=self._opts.port,
            timeout=self._opts.connect_timeout_ms / 1000.0,
        )
        ok = await self._client.connect()
        if ok:
            log.info("TCP connected to %s:%s", self._opts.host, self._opts.port)
        return bool(ok)
