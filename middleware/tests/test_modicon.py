import pytest

from driftwatch.domain.object_type import ModbusObjectType
from driftwatch.domain.modicon import ModiconAddress


@pytest.mark.parametrize("modicon,otype,addr", [
    (40001, ModbusObjectType.HOLDING_REGISTER, 0),
    (40101, ModbusObjectType.HOLDING_REGISTER, 100),
    (30001, ModbusObjectType.INPUT_REGISTER, 0),
    (1, ModbusObjectType.COIL, 0),       # 00001
    (10001, ModbusObjectType.DISCRETE_INPUT, 0),
])
def test_from_modicon(modicon, otype, addr):
    a = ModiconAddress.from_modicon(modicon)
    assert a.object_type is otype
    assert a.address == addr


@pytest.mark.parametrize("otype,addr,text", [
    (ModbusObjectType.HOLDING_REGISTER, 0, "40001"),
    (ModbusObjectType.HOLDING_REGISTER, 100, "40101"),
    (ModbusObjectType.INPUT_REGISTER, 0, "30001"),
    (ModbusObjectType.COIL, 0, "00001"),
    (ModbusObjectType.DISCRETE_INPUT, 0, "10001"),
])
def test_to_modicon_string(otype, addr, text):
    assert ModiconAddress.from_protocol(otype, addr).to_modicon_string() == text


def test_roundtrip_all_types():
    for otype in ModbusObjectType:
        for addr in (0, 1, 9998):
            s = ModiconAddress.from_protocol(otype, addr).to_modicon_string()
            back = ModiconAddress.from_modicon(int(s))
            assert (back.object_type, back.address) == (otype, addr)


def test_six_digit_form():
    # 1-based data > 9999 → 6-digit form
    a = ModiconAddress.from_protocol(ModbusObjectType.HOLDING_REGISTER, 10000)  # one-based 10001
    assert a.to_modicon_string() == "410001"
    assert ModiconAddress.from_modicon(410001).address == 10000


def test_invalid():
    with pytest.raises(ValueError):
        ModiconAddress.from_modicon(0)
    with pytest.raises(ValueError):
        ModiconAddress.from_modicon(20001)  # prefix 2 unknown
    with pytest.raises(ValueError):
        ModiconAddress.parse("abc")
