"""Modbus error types. The protocol-vs-transport split drives the resilience logic:
protocol errors are healthy device replies (no reconnect); transport errors fault the connection."""
from __future__ import annotations

# Illegal Data Address — the Modbus exception code that means "no such address here".
ILLEGAL_DATA_ADDRESS = 0x02


class ModbusProtocolException(Exception):
    """The device replied with a Modbus exception code. The connection is still healthy."""

    def __init__(self, code: int, message: str | None = None, *, unit_id: int | None = None,
                 function_code: int | None = None):
        self.code = code
        self.unit_id = unit_id
        self.function_code = function_code
        super().__init__(message or f"Modbus protocol exception (code {code})")

    @property
    def is_address_invalid(self) -> bool:
        return self.code == ILLEGAL_DATA_ADDRESS


class ModbusTransportException(Exception):
    """A transport-level failure (socket reset, serial timeout, CRC error, not connected).
    The connection should be assumed invalid until reconnected."""
