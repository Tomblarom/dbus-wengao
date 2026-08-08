from __future__ import annotations

from collections.abc import Iterable

from wengao.protocol.crc import append_crc


def holding_response(registers: Iterable[int], address: int = 1) -> bytes:
    values = tuple(registers)
    payload = b"".join(value.to_bytes(2, "big") for value in values)
    return append_crc(bytes((address, 3, len(payload))) + payload)
