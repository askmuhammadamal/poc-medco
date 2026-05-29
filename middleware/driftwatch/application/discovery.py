"""Walks the configured address range per object type per unit, classifying each address as
alive / dead (ILLEGAL_DATA_ADDRESS) / errored, with binary subdivision so one dead address
doesn't poison a batch."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ..domain.exceptions import ModbusProtocolException, ModbusTransportException
from ..domain.modicon import ModiconAddress
from ..domain.object_type import ModbusObjectType
from .discovery_report import (
    AliveRegister, DeadRange, DiscoveryReport, ErrorRange, ObjectTypeDiscovery, UnitDiscovery,
)
from .options import DiscoveryOptions
from .ports import ModbusClient
from .slave_scanner import SlaveScanner

log = logging.getLogger("driftwatch.discovery")


class AddressDiscoveryService:
    def __init__(self, client: ModbusClient, options: DiscoveryOptions, slave_scanner: SlaveScanner) -> None:
        self._client = client
        self._options = options
        self._slave_scanner = slave_scanner

    async def run(self) -> DiscoveryReport:
        report = DiscoveryReport(started_at=datetime.utcnow())
        if self._options.scan_slaves:
            units = await self._slave_scanner.scan(self._options.scan_slaves_max)
        else:
            units = list(self._options.slave_ids)
        report.responding_units.extend(units)
        if not units:
            log.warning("No slave IDs to scan. Set Discovery.SlaveIds or enable ScanSlaves.")

        for unit in units:
            unit_report = UnitDiscovery(unit_id=unit)
            for otype in self._options.object_types:
                log.info("Discovering %s on unit %s [%d..%d]", otype.value, unit,
                         self._options.address_range.start, self._options.address_range.end)
                unit_report.object_types.append(await self._discover_type(unit, otype))
            report.units.append(unit_report)

        report.completed_at = datetime.utcnow()
        return report

    async def _discover_type(self, unit: int, otype: ModbusObjectType) -> ObjectTypeDiscovery:
        result = ObjectTypeDiscovery(object_type=otype)
        batch_size = max(1, self._options.batch_size)
        pause_ms = max(0, self._options.pause_ms)
        start = self._options.address_range.start
        end_exclusive = min(0xFFFF, self._options.address_range.end + 1)

        cursor = start
        while cursor < end_exclusive:
            batch = min(batch_size, end_exclusive - cursor)
            await self._probe(unit, otype, cursor, batch, result)
            cursor += batch
            if pause_ms > 0:
                await asyncio.sleep(pause_ms / 1000.0)
        return result

    async def _probe(self, unit, otype, start, count, result: ObjectTypeDiscovery) -> None:
        try:
            values = await self._client.read(otype, unit, start, count)
            for i, v in enumerate(values):
                address = start + i
                result.alive.append(AliveRegister(
                    address=address,
                    modicon=ModiconAddress.from_protocol(otype, address).to_modicon_string(),
                    value=v,
                ))
        except ModbusProtocolException as exc:
            if exc.is_address_invalid:
                await self._bisect(unit, otype, start, count, result)
            else:
                result.errors.append(ErrorRange(start, start + count - 1, f"protocol exception {exc.code}"))
        except ModbusTransportException as exc:
            result.errors.append(ErrorRange(start, start + count - 1, f"transport: {exc}"))

    async def _bisect(self, unit, otype, start, count, result: ObjectTypeDiscovery) -> None:
        if count == 1:
            result.dead.append(DeadRange(start, start))
            return
        half = count // 2
        await self._probe(unit, otype, start, half, result)
        await self._probe(unit, otype, start + half, count - half, result)
