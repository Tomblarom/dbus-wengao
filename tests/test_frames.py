import pytest
from conftest import holding_response

from wengao.errors import CrcMismatchError, ModbusExceptionResponseError, UnexpectedResponseError
from wengao.protocol.crc import append_crc
from wengao.protocol.frame import (
    ReadHoldingRequest,
    WriteMultipleRegistersRequest,
    WriteSingleRegisterRequest,
    parse_read_holding_response,
    parse_write_multiple_response,
    parse_write_single_response,
)


def test_build_read_holding_request() -> None:
    request = ReadHoldingRequest(1, 0x0200, 16)
    assert request.to_frame() == bytes.fromhex("01030200001045BE")


@pytest.mark.parametrize(
    ("address", "start", "count"),
    [(0, 0, 1), (248, 0, 1), (1, -1, 1), (1, 0xFFFF, 2), (1, 0, 0), (1, 0, 126)],
)
def test_request_rejects_invalid_ranges(address: int, start: int, count: int) -> None:
    with pytest.raises(ValueError):
        ReadHoldingRequest(address, start, count).to_frame()


def test_parse_valid_response() -> None:
    frame = holding_response((0x1234, 0xABCD))
    assert parse_read_holding_response(frame, expected_address=1, expected_register_count=2) == (
        0x1234,
        0xABCD,
    )


def test_parse_rejects_bad_crc() -> None:
    frame = bytearray(holding_response((1,)))
    frame[-1] ^= 1
    with pytest.raises(CrcMismatchError):
        parse_read_holding_response(bytes(frame), expected_address=1, expected_register_count=1)


def test_parse_rejects_wrong_address() -> None:
    with pytest.raises(UnexpectedResponseError, match="slave address"):
        parse_read_holding_response(
            holding_response((1,), address=2), expected_address=1, expected_register_count=1
        )


def test_parse_rejects_wrong_function() -> None:
    frame = append_crc(bytes((1, 4, 2, 0, 1)))
    with pytest.raises(UnexpectedResponseError, match="function"):
        parse_read_holding_response(frame, expected_address=1, expected_register_count=1)


def test_parse_modbus_exception() -> None:
    frame = append_crc(bytes((1, 0x83, 2)))
    with pytest.raises(ModbusExceptionResponseError) as result:
        parse_read_holding_response(frame, expected_address=1, expected_register_count=1)
    assert result.value.exception_code == 2


def test_parse_rejects_short_response() -> None:
    with pytest.raises(UnexpectedResponseError, match="too short"):
        parse_read_holding_response(b"\x01\x03", expected_address=1, expected_register_count=1)


def test_parse_rejects_additional_bytes() -> None:
    body_with_extra_byte = bytes((1, 3, 2, 0, 1, 0x99))
    frame = append_crc(body_with_extra_byte)
    with pytest.raises(UnexpectedResponseError, match="frame length"):
        parse_read_holding_response(frame, expected_address=1, expected_register_count=1)


def test_parse_rejects_unexpected_byte_count() -> None:
    with pytest.raises(UnexpectedResponseError, match="byte count"):
        parse_read_holding_response(
            holding_response((1, 2)), expected_address=1, expected_register_count=1
        )


def test_build_and_parse_write_single_register() -> None:
    request = WriteSingleRegisterRequest(1, 0x0401, 0).to_frame()
    assert request == append_crc(bytes.fromhex("010604010000"))
    parse_write_single_response(
        request,
        expected_address=1,
        expected_register=0x0401,
        expected_value=0,
    )


def test_build_and_parse_write_multiple_registers() -> None:
    request = WriteMultipleRegistersRequest(1, 0x081D, (5840, 2500, 1500)).to_frame()
    assert request == append_crc(bytes.fromhex("0110081D00030616D009C405DC"))
    response = append_crc(bytes.fromhex("0110081D0003"))
    parse_write_multiple_response(
        response,
        expected_address=1,
        expected_start_register=0x081D,
        expected_count=3,
    )


def test_write_response_rejects_wrong_echo() -> None:
    response = append_crc(bytes.fromhex("010604010001"))
    with pytest.raises(UnexpectedResponseError, match="does not echo"):
        parse_write_single_response(
            response,
            expected_address=1,
            expected_register=0x0401,
            expected_value=0,
        )
