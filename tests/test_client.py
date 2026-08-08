from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import holding_response

from wengao.errors import UnsupportedDeviceError
from wengao.protocol.capture import CaptureWriter
from wengao.protocol.client import WengaoProtocol


class FakeTransport:
    def __init__(self, responses: list[bytes]) -> None:
        self.responses = responses
        self.requests: list[bytes] = []

    def exchange(self, request: bytes) -> bytes:
        self.requests.append(request)
        return self.responses.pop(0)


def identity_registers(model: str = "WG-BC1500M", address: int = 1) -> tuple[int, ...]:
    payload = bytearray(60)
    payload[0:4] = b"V101"
    payload[8:12] = b"V103"
    payload[12:16] = b"V201"
    payload[16:36] = b"PRIVATE-SERIAL-00001"
    payload[36:56] = model.encode("ascii").ljust(20)
    payload[56:58] = address.to_bytes(2, "big")
    return tuple(int.from_bytes(payload[i : i + 2], "big") for i in range(0, 60, 2))


def test_client_has_no_write_api() -> None:
    public_names = {name for name in dir(WengaoProtocol) if not name.startswith("_")}
    assert not any("write" in name.lower() for name in public_names)


def test_connection_accepts_observed_internal_model() -> None:
    transport = FakeTransport([holding_response(identity_registers())])
    identity = WengaoProtocol(transport).test_connection()
    assert identity.model == "WG-BC1500M"
    assert transport.requests == [bytes.fromhex("01030000001EC5C2")]


def test_connection_rejects_unknown_model() -> None:
    transport = FakeTransport([holding_response(identity_registers("OTHER"))])
    with pytest.raises(UnsupportedDeviceError, match="unsupported model"):
        WengaoProtocol(transport).test_connection()


def test_connection_rejects_identity_address_mismatch() -> None:
    transport = FakeTransport([holding_response(identity_registers(address=2))])
    with pytest.raises(UnsupportedDeviceError, match="reports address"):
        WengaoProtocol(transport).test_connection()


def test_identity_capture_redacts_response(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.jsonl"
    transport = FakeTransport([holding_response(identity_registers())])
    capture = CaptureWriter(capture_path, device_id="test-device", port_alias="test-port")
    WengaoProtocol(transport, capture=capture).read_identity()
    record = json.loads(capture_path.read_text(encoding="utf-8"))
    assert record["rx_hex"] is None
    assert record["rx_redacted"] is True
    assert record["rx_sha256"]
    assert "PRIVATE" not in capture_path.read_text(encoding="utf-8")
