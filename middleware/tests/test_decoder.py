import pytest

from driftwatch.domain import decoder as d
from driftwatch.domain.decoder import WordOrder


def test_int16_uint16():
    assert d.to_int16(0xFFFF) == -1
    assert d.to_int16(0x7FFF) == 32767
    assert d.to_int16(0x8000) == -32768
    assert d.to_uint16(0xFFFF) == 65535
    assert d.to_uint16(0x0000) == 0


def test_int32_uint32_abcd():
    assert d.to_int32([0x0001, 0x0002], WordOrder.ABCD) == 0x00010002
    assert d.to_uint32([0xFFFF, 0xFFFE], WordOrder.ABCD) == 0xFFFFFFFE
    assert d.to_int32([0xFFFF, 0xFFFF], WordOrder.ABCD) == -1


def test_float32_word_orders():
    # 1.0f big-endian = 3F 80 00 00  → ABCD registers [0x3F80, 0x0000]
    assert d.to_float32([0x3F80, 0x0000], WordOrder.ABCD) == pytest.approx(1.0)
    # CDAB = word-swapped
    assert d.to_float32([0x0000, 0x3F80], WordOrder.CDAB) == pytest.approx(1.0)
    # BADC = byte-swapped within each word
    assert d.to_float32([0x803F, 0x0000], WordOrder.BADC) == pytest.approx(1.0)
    # DCBA = word + byte swapped
    assert d.to_float32([0x0000, 0x803F], WordOrder.DCBA) == pytest.approx(1.0)


def test_int32_all_orders_consistent():
    # Same logical value 0x01020304 expressed per order, all decode equal under ABCD-equivalent.
    assert d.to_int32([0x0102, 0x0304], WordOrder.ABCD) == 0x01020304
    assert d.to_int32([0x0304, 0x0102], WordOrder.CDAB) == 0x01020304
    assert d.to_int32([0x0201, 0x0403], WordOrder.BADC) == 0x01020304
    assert d.to_int32([0x0403, 0x0201], WordOrder.DCBA) == 0x01020304


def test_int64_float64():
    assert d.to_int64([0x0000, 0x0000, 0x0000, 0x0001], WordOrder.ABCD) == 1
    assert d.to_float64([0x3FF0, 0x0000, 0x0000, 0x0000], WordOrder.ABCD) == pytest.approx(1.0)


def test_ascii_string():
    # "PLC" → 'P'=0x50 'L'=0x4C 'C'=0x43 pad 0x00 → [0x504C, 0x4300]
    assert d.to_ascii_string([0x504C, 0x4300], WordOrder.ABCD) == "PLC"
    assert d.to_ascii_string([0x4300, 0x504C], WordOrder.CDAB) == "PLC"
    # byte-swapped
    assert d.to_ascii_string([0x4C50, 0x0043], WordOrder.BADC) == "PLC"


def test_insufficient_registers():
    with pytest.raises(ValueError):
        d.to_int32([0x0001], WordOrder.ABCD)
    with pytest.raises(ValueError):
        d.to_int64([0x0001, 0x0002], WordOrder.ABCD)
