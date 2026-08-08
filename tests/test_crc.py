from wengao.protocol.crc import append_crc, crc16_modbus, verify_crc


def test_documented_read_request_crc() -> None:
    payload = bytes.fromhex("010302000010")
    assert crc16_modbus(payload) == 0xBE45
    assert append_crc(payload).hex().upper() == "01030200001045BE"


def test_verify_crc_rejects_corruption() -> None:
    frame = bytearray.fromhex("01030200001045BE")
    assert verify_crc(frame)
    frame[3] ^= 1
    assert not verify_crc(frame)


def test_verify_crc_rejects_too_short_frame() -> None:
    assert not verify_crc(b"\x01\x03\x00")
