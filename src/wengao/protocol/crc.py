"""Modbus RTU CRC16."""


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def append_crc(data: bytes) -> bytes:
    crc = crc16_modbus(data)
    return data + bytes((crc & 0xFF, crc >> 8))


def verify_crc(frame: bytes) -> bool:
    if len(frame) < 4:
        return False
    expected = int.from_bytes(frame[-2:], byteorder="little")
    return crc16_modbus(frame[:-2]) == expected
