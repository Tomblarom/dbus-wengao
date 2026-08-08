"""Construction and strict validation of read-only Modbus RTU frames."""

from __future__ import annotations

from dataclasses import dataclass

from wengao.errors import CrcMismatchError, ModbusExceptionResponseError, UnexpectedResponseError

from .crc import append_crc, verify_crc

READ_HOLDING_REGISTERS = 0x03
MIN_SLAVE_ADDRESS = 1
MAX_SLAVE_ADDRESS = 247
MAX_READ_REGISTERS = 125


@dataclass(frozen=True, slots=True)
class ReadHoldingRequest:
    slave_address: int
    start_register: int
    register_count: int

    def to_frame(self) -> bytes:
        validate_slave_address(self.slave_address)
        if not 0 <= self.start_register <= 0xFFFF:
            raise ValueError("start register must fit in 16 bits")
        if not 1 <= self.register_count <= MAX_READ_REGISTERS:
            raise ValueError(f"register count must be between 1 and {MAX_READ_REGISTERS}")
        if self.start_register + self.register_count > 0x10000:
            raise ValueError("requested register range overflows 16-bit address space")
        payload = bytes(
            (
                self.slave_address,
                READ_HOLDING_REGISTERS,
                self.start_register >> 8,
                self.start_register & 0xFF,
                self.register_count >> 8,
                self.register_count & 0xFF,
            )
        )
        return append_crc(payload)


def validate_slave_address(address: int) -> None:
    if not MIN_SLAVE_ADDRESS <= address <= MAX_SLAVE_ADDRESS:
        raise ValueError(
            f"slave address must be between {MIN_SLAVE_ADDRESS} and {MAX_SLAVE_ADDRESS}"
        )


def parse_read_holding_response(
    frame: bytes, *, expected_address: int, expected_register_count: int
) -> tuple[int, ...]:
    if len(frame) < 5:
        raise UnexpectedResponseError(f"response is too short: {len(frame)} bytes")
    if not verify_crc(frame):
        raise CrcMismatchError("response CRC does not match")
    if frame[0] != expected_address:
        raise UnexpectedResponseError(
            f"unexpected slave address 0x{frame[0]:02X}; expected 0x{expected_address:02X}"
        )
    function_code = frame[1]
    if function_code == (READ_HOLDING_REGISTERS | 0x80):
        if len(frame) != 5:
            raise UnexpectedResponseError("Modbus exception response has an invalid length")
        raise ModbusExceptionResponseError(READ_HOLDING_REGISTERS, frame[2])
    if function_code != READ_HOLDING_REGISTERS:
        raise UnexpectedResponseError(
            f"unexpected function 0x{function_code:02X}; expected 0x{READ_HOLDING_REGISTERS:02X}"
        )
    byte_count = frame[2]
    expected_byte_count = expected_register_count * 2
    if byte_count != expected_byte_count:
        raise UnexpectedResponseError(
            f"unexpected byte count {byte_count}; expected {expected_byte_count}"
        )
    expected_length = 3 + byte_count + 2
    if len(frame) != expected_length:
        raise UnexpectedResponseError(
            f"unexpected frame length {len(frame)}; expected exactly {expected_length}"
        )
    payload = frame[3:-2]
    return tuple(
        int.from_bytes(payload[index : index + 2], "big") for index in range(0, len(payload), 2)
    )
