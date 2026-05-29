"""RTU transport — wraps pymodbus AsyncModbusSerialClient.

On macOS use socat to create a virtual serial pair; on Windows use the USB-RS485 COM port.
"""
from __future__ import annotations

import logging

from pymodbus.client import AsyncModbusSerialClient

from ...application.options import ModbusOptions
from .pymodbus_base import PymodbusClientBase

log = logging.getLogger("driftwatch.transport.rtu")

_PARITY = {"N": "N", "E": "E", "O": "O", "NONE": "N", "EVEN": "E", "ODD": "O"}


class RtuModbusClient(PymodbusClientBase):
    def __init__(self, options: ModbusOptions) -> None:
        super().__init__()
        self._opts = options.rtu

    async def _open(self) -> bool:
        self._client = AsyncModbusSerialClient(
            port=self._opts.port_name,
            baudrate=self._opts.baud_rate,
            bytesize=self._opts.data_bits,
            parity=_PARITY.get(str(self._opts.parity).upper(), "N"),
            stopbits=self._opts.stop_bits,
            timeout=self._opts.read_timeout_ms / 1000.0,
        )
        ok = await self._client.connect()
        if ok:
            log.info("RTU connected on %s @ %s baud", self._opts.port_name, self._opts.baud_rate)
        return bool(ok)
