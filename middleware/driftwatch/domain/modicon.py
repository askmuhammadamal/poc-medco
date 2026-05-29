"""Modicon-style 5-/6-digit addressing.

Leading digit identifies the object type (0=Coil, 1=DiscreteInput, 3=InputRegister,
4=HoldingRegister); trailing digits are 1-based. Modicon 40001 == protocol holding register 0.
"""
from __future__ import annotations

from dataclasses import dataclass

from .object_type import ModbusObjectType

_PREFIX_TO_TYPE = {
    0: ModbusObjectType.COIL,
    1: ModbusObjectType.DISCRETE_INPUT,
    3: ModbusObjectType.INPUT_REGISTER,
    4: ModbusObjectType.HOLDING_REGISTER,
}
_TYPE_TO_PREFIX = {v: k for k, v in _PREFIX_TO_TYPE.items()}


@dataclass(frozen=True)
class ModiconAddress:
    object_type: ModbusObjectType
    address: int  # 0-based protocol address

    @staticmethod
    def from_protocol(object_type: ModbusObjectType, address: int) -> "ModiconAddress":
        return ModiconAddress(object_type, address)

    @staticmethod
    def from_modicon(modicon: int) -> "ModiconAddress":
        if modicon <= 0:
            raise ValueError(f"Modicon address must be positive: {modicon}")
        six_digit = modicon >= 100000
        prefix = modicon // 100000 if six_digit else modicon // 10000
        one_based = modicon % 100000 if six_digit else modicon % 10000
        if one_based <= 0:
            raise ValueError(f"Modicon address data part must be >=1: {modicon}")
        protocol = one_based - 1
        if protocol > 0xFFFF:
            raise ValueError(f"Modicon address overflows 16-bit space: {modicon}")
        if prefix not in _PREFIX_TO_TYPE:
            raise ValueError(f"Unknown Modicon prefix {prefix} in {modicon}")
        return ModiconAddress(_PREFIX_TO_TYPE[prefix], protocol)

    @staticmethod
    def parse(text: str) -> "ModiconAddress":
        if text is None or not text.strip():
            raise ValueError("Modicon address is empty.")
        try:
            value = int(text.strip())
        except ValueError as exc:
            raise ValueError(f"Modicon address not numeric: {text}") from exc
        return ModiconAddress.from_modicon(value)

    def to_modicon_string(self) -> str:
        """Render in 5-digit form when possible, else 6-digit."""
        prefix = _TYPE_TO_PREFIX[self.object_type]
        one_based = self.address + 1
        six_digit = one_based > 9999
        width = 6 if six_digit else 5
        multiplier = 100000 if six_digit else 10000
        composed = prefix * multiplier + one_based
        return f"{composed:0{width}d}"

    def __str__(self) -> str:
        return f"{self.to_modicon_string()} ({self.object_type.value} {self.address})"
