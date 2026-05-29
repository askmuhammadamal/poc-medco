"""Sweeps unit IDs 1..max with a cheap read, classifying each as responder (data OR a valid
Modbus exception both prove the device speaks the protocol) vs absent (transport fault)."""
from __future__ import annotations

import logging
from typing import List

from ..domain.exceptions import ModbusProtocolException, ModbusTransportException
from .ports import ModbusClient

log = logging.getLogger("driftwatch.discovery.slave")


class SlaveScanner:
    def __init__(self, client: ModbusClient) -> None:
        self._client = client

    async def scan(self, max_unit: int) -> List[int]:
        responders: List[int] = []
        for unit in range(1, max_unit + 1):
            try:
                await self._client.read_holding_registers(unit, 0, 1)
                responders.append(unit)  # responded with data
            except ModbusProtocolException:
                responders.append(unit)  # responded with an exception code → still speaks Modbus
            except ModbusTransportException:
                pass  # no response → absent
        log.info("Slave scan 1..%d → responders: %s", max_unit, responders)
        return responders
