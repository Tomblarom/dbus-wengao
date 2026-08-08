from __future__ import annotations

import json
from pathlib import Path

import pytest

from wengao.protocol.frame import parse_read_holding_response
from wengao.protocol.registers import decode_identity, decode_realtime


def test_anonymised_observed_realtime_frames() -> None:
    path = Path(__file__).parent / "fixtures" / "observed_realtime.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    for sample in fixture["samples"]:
        registers = parse_read_holding_response(
            bytes.fromhex(sample["response"]),
            expected_address=1,
            expected_register_count=16,
        )
        snapshot = decode_realtime(registers)
        expected = sample["expected"]
        assert snapshot.terminal_a.voltage_v == expected["terminal_a_voltage_v"]
        assert snapshot.terminal_a.current_a == expected["terminal_a_current_a"]
        assert snapshot.terminal_a.power_w == expected["terminal_a_power_w"]
        assert snapshot.terminal_b.voltage_v == expected["terminal_b_voltage_v"]
        assert snapshot.terminal_b.current_a == expected["terminal_b_current_a"]
        assert snapshot.terminal_b.power_w == expected["terminal_b_power_w"]
        assert snapshot.acc_voltage_v == expected["acc_voltage_v"]
        assert snapshot.rmt_voltage_v == expected["rmt_voltage_v"]
        assert snapshot.charging_state == expected["charging_state"]
        assert snapshot.plausibility_errors() == ()


def test_identity_layout_and_safe_mapping_omit_serial_number() -> None:
    payload = bytearray(60)
    payload[0:4] = b"V101"
    payload[8:12] = b"V103"
    payload[12:16] = b"V201"
    payload[16:36] = b"SYNTHETIC-0000000000"
    payload[36:56] = b"WG-BC1500M".ljust(20)
    payload[56:58] = (1).to_bytes(2, "big")
    registers = tuple(int.from_bytes(payload[i : i + 2], "big") for i in range(0, 60, 2))
    identity = decode_identity(registers)
    assert identity.model == "WG-BC1500M"
    assert identity.protocol_version == "V101"
    assert identity.serial_number == "SYNTHETIC-0000000000"
    assert "serial_number" not in identity.safe_mapping()
    assert "SYNTHETIC" not in repr(identity.safe_mapping())


def test_identity_rejects_wrong_block_length() -> None:
    with pytest.raises(Exception, match="identity block"):
        decode_identity((1, 2))


def test_unknown_state_is_preserved() -> None:
    registers = (0,) * 15 + (0xFFFF,)
    assert decode_realtime(registers).charging_state == 0xFFFF
