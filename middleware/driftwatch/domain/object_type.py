"""The four Modbus object types. Modicon prefixes: 0=Coil, 1=DiscreteInput, 3=InputRegister,
4=HoldingRegister."""
from __future__ import annotations

import enum


class ModbusObjectType(enum.Enum):
    COIL = "Coil"
    DISCRETE_INPUT = "DiscreteInput"
    INPUT_REGISTER = "InputRegister"
    HOLDING_REGISTER = "HoldingRegister"

    @property
    def is_bit(self) -> bool:
        return self in (ModbusObjectType.COIL, ModbusObjectType.DISCRETE_INPUT)

    @property
    def is_writable(self) -> bool:
        return self in (ModbusObjectType.COIL, ModbusObjectType.HOLDING_REGISTER)

    @property
    def read_function_code(self) -> int:
        return {
            ModbusObjectType.COIL: 1,
            ModbusObjectType.DISCRETE_INPUT: 2,
            ModbusObjectType.HOLDING_REGISTER: 3,
            ModbusObjectType.INPUT_REGISTER: 4,
        }[self]

    @classmethod
    def parse(cls, text: str) -> "ModbusObjectType":
        """Parse by enum name (e.g. 'HoldingRegister'), case-insensitive."""
        key = text.strip().lower()
        for member in cls:
            if member.value.lower() == key:
                return member
        raise ValueError(f"Unknown object type: {text!r}")
