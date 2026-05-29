"""Decode raw 16-bit registers into typed values across the four word orders.

Each register is big-endian on the wire (two bytes, MSB first); the WordOrder only changes how
multi-register values are reassembled.
"""
from __future__ import annotations

import enum
import struct


class WordOrder(enum.Enum):
    ABCD = "ABCD"  # big-endian
    CDAB = "CDAB"  # word-swapped
    BADC = "BADC"  # byte-swapped
    DCBA = "DCBA"  # word + byte swapped

    @classmethod
    def parse(cls, text: str) -> "WordOrder":
        return cls[text.strip().upper()]


def to_int16(register: int) -> int:
    return struct.unpack(">h", struct.pack(">H", register & 0xFFFF))[0]


def to_uint16(register: int) -> int:
    return register & 0xFFFF


def _ordered_bytes_32(registers, order: WordOrder) -> bytes:
    if len(registers) < 2:
        raise ValueError("32-bit decode requires at least 2 registers.")
    r0, r1 = registers[0] & 0xFFFF, registers[1] & 0xFFFF
    a, b = (r0 >> 8) & 0xFF, r0 & 0xFF
    c, d = (r1 >> 8) & 0xFF, r1 & 0xFF
    mapping = {
        WordOrder.ABCD: (a, b, c, d),
        WordOrder.CDAB: (c, d, a, b),
        WordOrder.BADC: (b, a, d, c),
        WordOrder.DCBA: (d, c, b, a),
    }
    return bytes(mapping[order])


def _ordered_bytes_64(registers, order: WordOrder) -> bytes:
    if len(registers) < 4:
        raise ValueError("64-bit decode requires at least 4 registers.")
    word_swap = order in (WordOrder.CDAB, WordOrder.DCBA)
    byte_swap = order in (WordOrder.BADC, WordOrder.DCBA)
    raw = bytearray(8)
    for i in range(4):
        dest = (3 - i) if word_swap else i
        reg = registers[i] & 0xFFFF
        hi, lo = (reg >> 8) & 0xFF, reg & 0xFF
        if byte_swap:
            raw[dest * 2], raw[dest * 2 + 1] = lo, hi
        else:
            raw[dest * 2], raw[dest * 2 + 1] = hi, lo
    return bytes(raw)


def to_int32(registers, order: WordOrder) -> int:
    return struct.unpack(">i", _ordered_bytes_32(registers, order))[0]


def to_uint32(registers, order: WordOrder) -> int:
    return struct.unpack(">I", _ordered_bytes_32(registers, order))[0]


def to_float32(registers, order: WordOrder) -> float:
    return struct.unpack(">f", _ordered_bytes_32(registers, order))[0]


def to_int64(registers, order: WordOrder) -> int:
    return struct.unpack(">q", _ordered_bytes_64(registers, order))[0]


def to_float64(registers, order: WordOrder) -> float:
    return struct.unpack(">d", _ordered_bytes_64(registers, order))[0]


def to_ascii_string(registers, order: WordOrder) -> str:
    """Decode an ASCII string. Each register holds two chars; word/byte swap per order.
    Trailing null padding is trimmed."""
    swap_words = order in (WordOrder.CDAB, WordOrder.DCBA)
    swap_bytes = order in (WordOrder.BADC, WordOrder.DCBA)
    n = len(registers)
    buffer = bytearray(n * 2)
    for i in range(n):
        dest = (n - 1 - i) if swap_words else i
        reg = registers[i] & 0xFFFF
        hi, lo = (reg >> 8) & 0xFF, reg & 0xFF
        if swap_bytes:
            buffer[dest * 2], buffer[dest * 2 + 1] = lo, hi
        else:
            buffer[dest * 2], buffer[dest * 2 + 1] = hi, lo
    return buffer.decode("ascii", errors="replace").rstrip("\x00")
