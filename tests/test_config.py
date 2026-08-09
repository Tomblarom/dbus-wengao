from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

import pytest

from wengao._vendor import tomli as vendored_tomli
from wengao.config import UnavailableDeviceDisplay, load_config, parse_config
from wengao.errors import ConfigurationError
from wengao.profiles import BUILTIN_PROFILES, ControlMode, Direction, DvccPolicy, VenusRole


def valid_device(**updates: Any) -> dict[str, Any]:
    device: dict[str, Any] = {
        "id": "device-1",
        "enabled": True,
        "profile": "bidirectional-battery-link",
        "port": "/dev/serial/by-id/synthetic-port-1",
        "slave_address": 1,
        "system_terminal": "B",
        "device_instance": 40,
        "custom_name": "Wengao DC-DC",
        "venus_role": "dcsystem",
        "control_mode": "monitor-only",
        "dvcc_policy": "disabled",
        "communication_timeout": 1.0,
        "poll_interval": 2.0,
        "allowed_directions": ["A-to-B", "B-to-A"],
        "locked_direction": "",
        "permissions": {},
    }
    device.update(updates)
    return device


def config_with(*devices: dict[str, Any]) -> dict[str, Any]:
    return {"config_version": 1, "devices": list(devices)}


def test_disabled_example_configuration_loads() -> None:
    path = Path(__file__).parents[1] / "config" / "config.example.toml"
    config = load_config(path)
    assert config.enabled_devices() == ()
    device = config.devices[0]
    assert device.control_mode is ControlMode.MONITOR_ONLY
    assert device.dvcc_policy is DvccPolicy.DISABLED
    assert not device.permissions.any_enabled()
    assert device.auxiliary_battery is not None
    assert not device.auxiliary_battery.enabled
    assert config.display.unavailable_devices is UnavailableDeviceDisplay.HIDE


def test_vendored_tomli_can_parse_example_for_stripped_venus_python() -> None:
    path = Path(__file__).parents[1] / "config" / "config.example.toml"
    with path.open("rb") as handle:
        parsed = vendored_tomli.load(handle)
    assert parsed["config_version"] == 1
    assert parsed["devices"][0]["enabled"] is False


def test_schema_is_valid_json() -> None:
    import json

    path = Path(__file__).parents[1] / "config" / "config.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("2020-12/schema")


def test_profile_toml_files_match_embedded_profiles() -> None:
    profile_directory = Path(__file__).parents[1] / "profiles"
    for path in profile_directory.glob("*.toml"):
        with path.open("rb") as handle:
            profile = tomllib.load(handle)
        assert profile["id"] == path.stem
        embedded = BUILTIN_PROFILES[path.stem]
        assert set(profile["venus_roles"]) == {role.value for role in embedded.allowed_venus_roles}
        assert profile["default_venus_role"] == embedded.default_venus_role.value


@pytest.mark.parametrize("version", [None, 0, 2, "1"])
def test_rejects_unsupported_config_version(version: object) -> None:
    with pytest.raises(ConfigurationError, match="config_version"):
        parse_config({"config_version": version, "devices": []})


def test_rejects_unknown_key() -> None:
    raw = config_with(valid_device(unsafe_fallback=True))
    with pytest.raises(ConfigurationError, match="unknown keys"):
        parse_config(raw)


def test_display_can_keep_unavailable_devices_visible_as_zero() -> None:
    raw = config_with(valid_device())
    raw["display"] = {"unavailable_devices": "zero"}
    parsed = parse_config(raw)
    assert parsed.display.unavailable_devices is UnavailableDeviceDisplay.ZERO


def test_display_order_follows_the_devices_array() -> None:
    second = valid_device(id="device-2", port="/dev/ttyS2", device_instance=41)
    parsed = parse_config(config_with(valid_device(), second))
    assert [device.display_order for device in parsed.devices] == [0, 1]


def test_vehicle_battery_link_defaults_to_alternator_role() -> None:
    device = valid_device(profile="vehicle-battery-link")
    del device["venus_role"]
    parsed = parse_config(config_with(device))
    assert parsed.devices[0].venus_role is VenusRole.ALTERNATOR


def test_rejects_unknown_unavailable_device_display() -> None:
    raw = config_with(valid_device())
    raw["display"] = {"unavailable_devices": "invented"}
    with pytest.raises(ConfigurationError, match=r"display\.unavailable_devices"):
        parse_config(raw)


def test_rejects_duplicate_device_ids() -> None:
    second = valid_device(port="/dev/ttyS2", device_instance=41)
    with pytest.raises(ConfigurationError, match="duplicate device id"):
        parse_config(config_with(valid_device(), second))


def test_rejects_duplicate_enabled_ports() -> None:
    second = valid_device(id="device-2", device_instance=41)
    with pytest.raises(ConfigurationError, match="assigned to multiple"):
        parse_config(config_with(valid_device(), second))


def test_disabled_device_may_share_port() -> None:
    second = valid_device(id="device-2", enabled=False, device_instance=41)
    assert len(parse_config(config_with(valid_device(), second)).devices) == 2


def test_rejects_duplicate_device_instance_within_class() -> None:
    second = valid_device(id="device-2", port="/dev/ttyS2")
    with pytest.raises(ConfigurationError, match="DeviceInstance"):
        parse_config(config_with(valid_device(), second))


def test_auxiliary_battery_is_read_from_other_terminal() -> None:
    auxiliary = {
        "enabled": True,
        "terminal": "A",
        "device_instance": 80,
        "custom_name": "Auxiliary battery",
    }
    parsed = parse_config(
        config_with(valid_device(system_terminal="B", auxiliary_battery=auxiliary))
    )
    assert parsed.devices[0].auxiliary_battery is not None
    assert parsed.devices[0].auxiliary_battery.terminal.value == "A"


def test_rejects_auxiliary_battery_on_system_terminal() -> None:
    auxiliary = {
        "enabled": True,
        "terminal": "B",
        "device_instance": 80,
        "custom_name": "Auxiliary battery",
    }
    with pytest.raises(ConfigurationError, match="must differ from system_terminal"):
        parse_config(config_with(valid_device(system_terminal="B", auxiliary_battery=auxiliary)))


def test_rejects_enabled_auxiliary_battery_for_disabled_device() -> None:
    auxiliary = {
        "enabled": True,
        "terminal": "A",
        "device_instance": 80,
        "custom_name": "Auxiliary battery",
    }
    with pytest.raises(ConfigurationError, match="disabled device"):
        parse_config(config_with(valid_device(enabled=False, auxiliary_battery=auxiliary)))


def test_rejects_duplicate_auxiliary_battery_instances() -> None:
    auxiliary = {
        "enabled": True,
        "terminal": "A",
        "device_instance": 80,
        "custom_name": "Auxiliary battery",
    }
    first = valid_device(auxiliary_battery=auxiliary)
    second = valid_device(
        id="device-2",
        port="/dev/ttyS2",
        device_instance=41,
        auxiliary_battery=auxiliary,
    )
    with pytest.raises(ConfigurationError, match="class battery"):
        parse_config(config_with(first, second))


def test_allows_same_device_instance_in_different_classes() -> None:
    second = valid_device(
        id="device-2",
        port="/dev/ttyS2",
        profile="fixed-direction-dc-converter",
        venus_role="dcdc",
        allowed_directions=["A-to-B"],
        locked_direction="A-to-B",
    )
    config = parse_config(config_with(valid_device(), second))
    assert {device.venus_role for device in config.devices} == {
        VenusRole.DC_SYSTEM,
        VenusRole.DC_DC,
    }


def test_rejects_active_placeholder_port() -> None:
    with pytest.raises(ConfigurationError, match="placeholder"):
        parse_config(config_with(valid_device(port="/dev/serial/by-id/REPLACE_ME")))


def test_rejects_by_path_alias() -> None:
    with pytest.raises(ConfigurationError, match="by-id"):
        parse_config(config_with(valid_device(port="/dev/serial/by-path/synthetic-port-1")))


@pytest.mark.parametrize("address", [0, 248, -1])
def test_rejects_invalid_slave_address(address: int) -> None:
    with pytest.raises(ConfigurationError, match="slave_address"):
        parse_config(config_with(valid_device(slave_address=address)))


def test_rejects_missing_port_when_runtime_check_is_enabled(tmp_path: Path) -> None:
    missing = f"/dev/serial/by-id/{tmp_path.name}-missing"
    with pytest.raises(ConfigurationError, match="does not exist"):
        parse_config(config_with(valid_device(port=missing)), require_ports_exist=True)


def test_rejects_profile_role_conflict() -> None:
    with pytest.raises(ConfigurationError, match="incompatible"):
        parse_config(config_with(valid_device(venus_role="alternator")))


def test_fixed_direction_requires_exact_lock() -> None:
    device = valid_device(
        profile="fixed-direction-dc-converter",
        venus_role="dcdc",
        allowed_directions=["A-to-B", "B-to-A"],
        locked_direction="A-to-B",
    )
    with pytest.raises(ConfigurationError, match="requires exactly one"):
        parse_config(config_with(device))


def test_fixed_direction_accepts_either_physical_direction() -> None:
    device = valid_device(
        profile="fixed-direction-dc-converter",
        venus_role="dcdc",
        allowed_directions=["B-to-A"],
        locked_direction="B-to-A",
    )
    parsed = parse_config(config_with(device)).devices[0]
    assert parsed.allowed_directions == (Direction.B_TO_A,)
    assert parsed.locked_direction is Direction.B_TO_A


def test_fixed_direction_can_publish_as_dc_system() -> None:
    device = valid_device(
        profile="fixed-direction-dc-converter",
        venus_role="dcsystem",
        allowed_directions=["A-to-B"],
        locked_direction="A-to-B",
    )
    parsed = parse_config(config_with(device)).devices[0]
    assert parsed.venus_role is VenusRole.DC_SYSTEM


def test_rejects_locked_direction_outside_allowed_set() -> None:
    with pytest.raises(ConfigurationError, match="included"):
        parse_config(
            config_with(valid_device(allowed_directions=["A-to-B"], locked_direction="B-to-A"))
        )


@pytest.mark.parametrize(
    "permission",
    [
        "remote_on_off",
        "set_voltage",
        "set_current",
        "set_direction",
        "set_mode",
        "set_protection_limits",
        "calibration",
        "factory_reset",
    ],
)
def test_monitor_only_rejects_every_write_permission(permission: str) -> None:
    permissions = {permission: True}
    with pytest.raises(ConfigurationError, match="enables writes"):
        parse_config(config_with(valid_device(permissions=permissions)))


def test_external_dbus_control_requires_explicit_destination_limits() -> None:
    device = valid_device(
        profile="fixed-direction-dc-converter",
        venus_role="dcdc",
        control_mode="external-dbus",
        allowed_directions=["A-to-B"],
        locked_direction="A-to-B",
        permissions={"set_voltage": True},
    )
    with pytest.raises(ConfigurationError, match="terminal_b_voltage is required"):
        parse_config(config_with(device))


def test_external_dbus_control_accepts_narrow_hardware_safe_limits() -> None:
    device = valid_device(
        profile="fixed-direction-dc-converter",
        venus_role="dcdc",
        control_mode="external-dbus",
        allowed_directions=["A-to-B"],
        locked_direction="A-to-B",
        permissions={"remote_on_off": True, "set_voltage": True, "set_current": True},
        write_limits={
            "minimum_interval": 5,
            "terminal_b_voltage": [48.0, 58.4],
            "terminal_b_current": [1.0, 25.0],
        },
    )
    parsed = parse_config(config_with(device)).devices[0]
    assert parsed.control_mode is ControlMode.EXTERNAL_DBUS
    assert parsed.write_limits.terminal_b_voltage is not None
    assert parsed.write_limits.terminal_b_voltage.maximum == 58.4


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("terminal_b_voltage", [9.0, 58.4], "10..60 V"),
        ("terminal_b_current", [1.0, 26.0], "1..25 A"),
    ],
)
def test_external_dbus_limits_cannot_exceed_hardware(
    key: str, value: list[float], message: str
) -> None:
    limits = {
        "terminal_b_voltage": [48.0, 58.4],
        "terminal_b_current": [1.0, 25.0],
    }
    limits[key] = value
    device = valid_device(
        profile="fixed-direction-dc-converter",
        venus_role="dcdc",
        control_mode="external-dbus",
        allowed_directions=["A-to-B"],
        locked_direction="A-to-B",
        permissions={"set_voltage": True, "set_current": True},
        write_limits=limits,
    )
    with pytest.raises(ConfigurationError, match=message):
        parse_config(config_with(device))


def test_rejects_unimplemented_dvcc() -> None:
    raw = config_with(valid_device())
    modified = copy.deepcopy(raw)
    modified["devices"][0]["dvcc_policy"] = "enabled"
    with pytest.raises(ConfigurationError, match="dvcc_policy"):
        parse_config(modified)


def test_device_lookup_fails_clearly() -> None:
    config = parse_config(config_with(valid_device()))
    with pytest.raises(ConfigurationError, match="not configured"):
        config.device("missing")
