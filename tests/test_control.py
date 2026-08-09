from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from wengao.config import DeviceConfig, parse_config
from wengao.control import SafeWriteController
from wengao.errors import UnsafeWriteError
from wengao.model import ControlSettings, DeviceIdentity, TerminalSetpoints
from wengao.profiles import Terminal


class FakeProtocol:
    def __init__(self) -> None:
        self.settings = ControlSettings(
            remote_enabled=True,
            terminal_a=TerminalSetpoints(14.4, 50.0, 720),
            terminal_b=TerminalSetpoints(54.0, 20.0, 1080),
        )
        self.writes: list[tuple[str, object]] = []
        self.fail_readback = False

    def read_control_settings(self) -> ControlSettings:
        return self.settings

    def read_remote_enabled(self) -> bool:
        return self.settings.remote_enabled

    def read_terminal_setpoints(self, terminal: str) -> TerminalSetpoints:
        if self.fail_readback:
            raise OSError("synthetic readback timeout")
        return self.settings.terminal_a if terminal == "A" else self.settings.terminal_b

    def write_remote_enabled(self, enabled: bool) -> None:
        self.writes.append(("remote", enabled))
        self.settings = replace(self.settings, remote_enabled=enabled)

    def write_terminal_voltage(self, terminal: str, voltage_v: float) -> None:
        current = self.settings.terminal_a if terminal == "A" else self.settings.terminal_b
        updated = replace(current, voltage_v=voltage_v)
        self.writes.append((f"{terminal}-voltage", voltage_v))
        self.settings = (
            replace(self.settings, terminal_a=updated)
            if terminal == "A"
            else replace(self.settings, terminal_b=updated)
        )

    def write_terminal_current(self, terminal: str, current_a: float) -> None:
        current = self.settings.terminal_a if terminal == "A" else self.settings.terminal_b
        updated = replace(current, current_a=current_a)
        self.writes.append((f"{terminal}-current", current_a))
        self.settings = (
            replace(self.settings, terminal_a=updated)
            if terminal == "A"
            else replace(self.settings, terminal_b=updated)
        )


def controlled_config() -> DeviceConfig:
    raw: dict[str, Any] = {
        "config_version": 1,
        "devices": [
            {
                "id": "controlled",
                "enabled": True,
                "profile": "fixed-direction-dc-converter",
                "port": "/dev/serial/by-id/synthetic",
                "slave_address": 1,
                "system_terminal": "A",
                "device_instance": 40,
                "custom_name": "Controlled converter",
                "venus_role": "dcdc",
                "control_mode": "external-dbus",
                "dvcc_policy": "disabled",
                "allowed_directions": ["A-to-B"],
                "locked_direction": "A-to-B",
                "permissions": {
                    "remote_on_off": True,
                    "set_voltage": True,
                    "set_current": True,
                },
                "write_limits": {
                    "minimum_interval": 5,
                    "terminal_b_voltage": [48.0, 58.4],
                    "terminal_b_current": [1.0, 25.0],
                },
            }
        ],
    }
    return parse_config(raw).devices[0]


def identity() -> DeviceIdentity:
    return DeviceIdentity("V101", "V103", "V201", "SYNTHETIC", "WG-BC1500M", 1, 0)


def test_write_is_locked_until_identity_is_verified() -> None:
    protocol = FakeProtocol()
    controller = SafeWriteController(protocol, controlled_config())
    with pytest.raises(UnsafeWriteError, match="identity"):
        controller.set_voltage(Terminal.B, 55.0)
    assert protocol.writes == []


def test_voltage_write_preserves_current_and_power_and_reads_back() -> None:
    protocol = FakeProtocol()
    controller = SafeWriteController(protocol, controlled_config())
    controller.authorize_identity(identity())
    verified = controller.set_voltage(Terminal.B, 55.2)
    assert protocol.writes == [("B-voltage", 55.2)]
    assert verified.terminal_b == TerminalSetpoints(55.2, 20.0, 1080)


def test_identical_value_does_not_write() -> None:
    protocol = FakeProtocol()
    controller = SafeWriteController(protocol, controlled_config())
    controller.authorize_identity(identity())
    controller.set_current(Terminal.B, 20.0)
    assert protocol.writes == []


def test_out_of_range_value_is_rejected_without_write() -> None:
    protocol = FakeProtocol()
    controller = SafeWriteController(protocol, controlled_config())
    controller.authorize_identity(identity())
    with pytest.raises(UnsafeWriteError, match="outside configured range"):
        controller.set_current(Terminal.B, 25.01)
    assert protocol.writes == []


def test_rate_limit_applies_per_persistent_register_block() -> None:
    now = 100.0
    protocol = FakeProtocol()
    controller = SafeWriteController(
        protocol, controlled_config(), monotonic=lambda: now
    )
    controller.authorize_identity(identity())
    controller.set_voltage(Terminal.B, 55.0)
    with pytest.raises(UnsafeWriteError, match="rate limit"):
        controller.set_current(Terminal.B, 21.0)
    assert len(protocol.writes) == 1


def test_ambiguous_write_failure_revokes_authorization_and_is_not_retried() -> None:
    protocol = FakeProtocol()
    controller = SafeWriteController(protocol, controlled_config())
    controller.authorize_identity(identity())
    protocol.fail_readback = True

    with pytest.raises(OSError, match="readback timeout"):
        controller.set_voltage(Terminal.B, 55.0)

    assert protocol.writes == [("B-voltage", 55.0)]
    assert controller.identity_verified is False
    with pytest.raises(UnsafeWriteError, match="identity"):
        controller.set_voltage(Terminal.B, 55.0)
    assert protocol.writes == [("B-voltage", 55.0)]

    # Even after a new identity handshake, an ambiguous persistent-write attempt remains
    # rate-limited. Simulate the device still reporting the previous value.
    protocol.fail_readback = False
    protocol.settings = replace(
        protocol.settings,
        terminal_b=replace(protocol.settings.terminal_b, voltage_v=54.0),
    )
    controller.authorize_identity(identity())
    with pytest.raises(UnsafeWriteError, match="rate limit"):
        controller.set_voltage(Terminal.B, 55.0)
    assert protocol.writes == [("B-voltage", 55.0)]
