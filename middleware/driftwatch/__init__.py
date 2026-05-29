"""Modbus client middleware — Python port of the .NET data-logger.

Continuously scans Modbus register ranges and emits change events (console / CSV / live SSE),
or discovers what a device actually exposes. Transport-agnostic (TCP / RTU) behind a resilient,
write-guarded client pipeline, with a single FastAPI service hosting the dashboard.
"""

__version__ = "1.0.0"
