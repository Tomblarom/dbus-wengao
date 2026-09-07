"""Construction and strict validation of supported Modbus RTU frames."""

from __future__ import annotations

from dataclasses import dataclass

from wengao.errors import CrcMismatchError, ModbusExceptionResponseError, UnexpectedResponseError

from .crc import append_crc, verify_crc

READ_HOLDING_REGISTERS = 0x03
WRITE_SINGLE_REGISTER = 0x06
WRITE_MULTIPLE_REGISTERS = 0x10
MIN_SLAVE_ADDRESS = 1
MAX_SLAVE_ADDRESS = 247
MAX_READ_REGISTERS = 125
MAX_WRITE_REGISTERS = 123


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


@dataclass(frozen=True, slots=True)
class WriteSingleRegisterRequest:
    slave_address: int
    register: int
    value: int

    def to_frame(self) -> bytes:
        validate_slave_address(self.slave_address)
        _validate_register(self.register)
        _validate_register_value(self.value)
        return append_crc(
            bytes(
                (
                    self.slave_address,
                    WRITE_SINGLE_REGISTER,
                    self.register >> 8,
                    self.register & 0xFF,
                    self.value >> 8,
                    self.value & 0xFF,
                )
            )
        )


@dataclass(frozen=True, slots=True)
class WriteMultipleRegistersRequest:
    slave_address: int
    start_register: int
    values: tuple[int, ...]

    def to_frame(self) -> bytes:
        validate_slave_address(self.slave_address)
        _validate_register(self.start_register)
        if not 1 <= len(self.values) <= MAX_WRITE_REGISTERS:
            raise ValueError(f"register count must be between 1 and {MAX_WRITE_REGISTERS}")
        if self.start_register + len(self.values) > 0x10000:
            raise ValueError("requested register range overflows 16-bit address space")
        for value in self.values:
            _validate_register_value(value)
        data = b"".join(value.to_bytes(2, "big") for value in self.values)
        payload = bytes(
            (
                self.slave_address,
                WRITE_MULTIPLE_REGISTERS,
                self.start_register >> 8,
                self.start_register & 0xFF,
                len(self.values) >> 8,
                len(self.values) & 0xFF,
                len(data),
            )
        ) + data
        return append_crc(payload)


def validate_slave_address(address: int) -> None:
    if not MIN_SLAVE_ADDRESS <= address <= MAX_SLAVE_ADDRESS:
        raise ValueError(
            f"slave address must be between {MIN_SLAVE_ADDRESS} and {MAX_SLAVE_ADDRESS}"
        )


def _validate_register(register: int) -> None:
    if not 0 <= register <= 0xFFFF:
        raise ValueError("register must fit in 16 bits")


def _validate_register_value(value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFF:
        raise ValueError("register value must be an integer that fits in 16 bits")


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


def parse_write_single_response(
    frame: bytes, *, expected_address: int, expected_register: int, expected_value: int
) -> None:
    _parse_write_response_header(frame, expected_address, WRITE_SINGLE_REGISTER)
    if len(frame) != 8:
        raise UnexpectedResponseError(
            f"unexpected frame length {len(frame)}; expected exactly 8"
        )
    register = int.from_bytes(frame[2:4], "big")
    value = int.from_bytes(frame[4:6], "big")
    if register != expected_register or value != expected_value:
        raise UnexpectedResponseError(
            "write-single response does not echo the requested register and value"
        )


def parse_write_multiple_response(
    frame: bytes, *, expected_address: int, expected_start_register: int, expected_count: int
) -> None:
    _parse_write_response_header(frame, expected_address, WRITE_MULTIPLE_REGISTERS)
    if len(frame) != 8:
        raise UnexpectedResponseError(
            f"unexpected frame length {len(frame)}; expected exactly 8"
        )
    start_register = int.from_bytes(frame[2:4], "big")
    count = int.from_bytes(frame[4:6], "big")
    if start_register != expected_start_register or count != expected_count:
        raise UnexpectedResponseError(
            "write-multiple response does not echo the requested range"
        )


def _parse_write_response_header(frame: bytes, expected_address: int, function_code: int) -> None:
    if len(frame) < 5:
        raise UnexpectedResponseError(f"response is too short: {len(frame)} bytes")
    if not verify_crc(frame):
        raise CrcMismatchError("response CRC does not match")
    if frame[0] != expected_address:
        raise UnexpectedResponseError(
            f"unexpected slave address 0x{frame[0]:02X}; expected 0x{expected_address:02X}"
        )
    if frame[1] == (function_code | 0x80):
        if len(frame) != 5:
            raise UnexpectedResponseError("Modbus exception response has an invalid length")
        raise ModbusExceptionResponseError(function_code, frame[2])
    if frame[1] != function_code:
        raise UnexpectedResponseError(
            f"unexpected function 0x{frame[1]:02X}; expected 0x{function_code:02X}"
        )
