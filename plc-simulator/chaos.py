"""Chaos middleware for the Modbus simulator.

Wraps a pymodbus ModbusSlaveContext to inject:
  - Random response delays (simulates slow PLCs / loaded networks)
  - Random Modbus exceptions (SERVER_DEVICE_BUSY / SLAVE_DEVICE_FAILURE)
  - Address gaps (ILLEGAL_DATA_ADDRESS for unallocated ranges)

Parse a chaos spec via parse_spec():
    "delay=50-500,error=0.02,gaps=0"

Gaps are a separate concept (driven by the loaded register map). The chaos layer
only adds runtime noise on top of whatever the underlying datastore exposes.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

from pymodbus.datastore import ModbusSlaveContext
from pymodbus.exceptions import ModbusIOException
from pymodbus.pdu import ExceptionResponse

log = logging.getLogger(__name__)


@dataclass
class ChaosSpec:
    delay_min_ms: int = 0
    delay_max_ms: int = 0
    error_rate: float = 0.0   # probability per request

    @property
    def enabled(self) -> bool:
        return self.delay_max_ms > 0 or self.error_rate > 0


def parse_spec(text: str | None) -> ChaosSpec:
    """Parse 'delay=50-500,error=0.02' style spec. Empty/None -> disabled."""
    spec = ChaosSpec()
    if not text:
        return spec
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        if "=" not in token:
            raise ValueError(f"Bad chaos token (expected key=value): {token!r}")
        key, value = token.split("=", 1)
        key, value = key.strip().lower(), value.strip()
        if key == "delay":
            if "-" in value:
                lo, hi = value.split("-", 1)
                spec.delay_min_ms = int(lo)
                spec.delay_max_ms = int(hi)
            else:
                spec.delay_min_ms = spec.delay_max_ms = int(value)
        elif key == "error":
            spec.error_rate = float(value)
            if not 0.0 <= spec.error_rate <= 1.0:
                raise ValueError("error rate must be in [0, 1]")
        else:
            raise ValueError(f"Unknown chaos key: {key!r}")
    return spec


class ChaosSlaveContext(ModbusSlaveContext):
    """ModbusSlaveContext that occasionally sleeps or raises Modbus exceptions.

    Inherits validate() / getValues() / setValues() from the parent and intercepts each call.
    """

    def __init__(self, inner: ModbusSlaveContext, spec: ChaosSpec):
        # Copy the inner store mapping rather than calling super().__init__()
        # so we share the actual data blocks (di/co/ir/hr) — no double allocation.
        self.store = inner.store
        self.zero_mode = inner.zero_mode
        self._spec = spec

    def _maybe_inject(self) -> None:
        if not self._spec.enabled:
            return
        if self._spec.delay_max_ms > 0:
            delay_ms = random.randint(self._spec.delay_min_ms, self._spec.delay_max_ms)
            time.sleep(delay_ms / 1000.0)
        if self._spec.error_rate > 0 and random.random() < self._spec.error_rate:
            # Raising ModbusIOException causes pymodbus to return SLAVE_DEVICE_FAILURE.
            log.debug("chaos: injecting fault")
            raise ModbusIOException("chaos: simulated transient failure")

    def validate(self, fc_as_hex, address, count=1):
        self._maybe_inject()
        return super().validate(fc_as_hex, address, count)

    def getValues(self, fc_as_hex, address, count=1):
        # Inject only in validate() to avoid double-delay per request.
        return super().getValues(fc_as_hex, address, count)

    def setValues(self, fc_as_hex, address, values):
        return super().setValues(fc_as_hex, address, values)
