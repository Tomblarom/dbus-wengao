from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import holding_response

from wengao.errors import UnsupportedDeviceError
from wengao.protocol.capture import CaptureWriter
from wengao.protocol.client import WengaoProtocol
from wengao.protocol.crc import append_crc


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


def test_client_exposes_only_the_confirmed_write_operations() -> None:
    public_names = {name for name in dir(WengaoProtocol) if not name.startswith("_")}
    write_names = {name for name in public_names if "write" in name.lower()}
    assert write_names == {
        "write_remote_enabled",
        "write_terminal_current",
        "write_terminal_voltage",
    }
    assert not any(
        dangerous in name.lower()
        for name in public_names
        for dangerous in ("factory", "calibration", "protection", "direction", "mode")
    )


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


def test_remote_control_write_validates_echo() -> None:
    response = append_crc(bytes.fromhex("010604010001"))
    transport = FakeTransport([response])
    WengaoProtocol(transport).write_remote_enabled(False)
    assert transport.requests == [append_crc(bytes.fromhex("010604010001"))]


def test_terminal_voltage_write_uses_single_register_like_android_app() -> None:
    response = append_crc(bytes.fromhex("0106081D157C"))
    transport = FakeTransport([response])
    WengaoProtocol(transport).write_terminal_voltage("B", 55.0)
    assert transport.requests == [append_crc(bytes.fromhex("0106081D157C"))]


def test_read_control_settings_decodes_remote_and_both_terminals() -> None:
    transport = FakeTransport(
        [
            holding_response((0,)),
            holding_response((1440, 5000, 720)),
            holding_response((5400, 2000, 1080)),
        ]
    )
    settings = WengaoProtocol(transport).read_control_settings()
    assert settings.remote_enabled is True
    assert settings.terminal_a.voltage_v == 14.4
    assert settings.terminal_b.current_a == 20.0
