"""Connection state of a Modbus client."""
from __future__ import annotations

import enum


class ConnectionState(enum.Enum):
    DISCONNECTED = "Disconnected"
    CONNECTING = "Connecting"
    CONNECTED = "Connected"
    FAULTED = "Faulted"
