"""Strict TOML configuration loading with fail-closed defaults."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from enum import StrEnum
from importlib import import_module
from pathlib import Path
from typing import Any, TypeVar, cast

try:
    toml_parser: Any = import_module("tomllib")
except ModuleNotFoundError:  # Some stripped Venus OS Python builds omit tomllib.
    toml_parser = import_module("wengao._vendor.tomli")

from wengao.errors import ConfigurationError
from wengao.profiles import (
    BUILTIN_PROFILES,
    ControlMode,
    Direction,
    DvccPolicy,
    Profile,
    Terminal,
    VenusRole,
)

CONFIG_VERSION = 1
MAX_DEVICE_INSTANCE = 32767
DEVICE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
STABLE_SERIAL_PREFIX = "/dev/serial/by-id/"


class UnavailableDeviceDisplay(StrEnum):
    HIDE = "hide"
    ZERO = "zero"


@dataclass(frozen=True, slots=True)
class DevicePermissions:
    remote_on_off: bool = False
    set_voltage: bool = False
    set_current: bool = False
    set_direction: bool = False
    set_mode: bool = False
    set_protection_limits: bool = False
    calibration: bool = False
    factory_reset: bool = False

    def any_enabled(self) -> bool:
        return any(getattr(self, field.name) for field in fields(self))


@dataclass(frozen=True, slots=True)
class AuxiliaryBatteryConfig:
    enabled: bool
    terminal: Terminal
    device_instance: int
    custom_name: str


@dataclass(frozen=True, slots=True)
class DeviceConfig:
    id: str
    enabled: bool
    profile: Profile
    port: str
    slave_address: int
    system_terminal: Terminal
    device_instance: int
    custom_name: str
    venus_role: VenusRole
    control_mode: ControlMode
    dvcc_policy: DvccPolicy
    communication_timeout: float
    poll_interval: float
    allowed_directions: tuple[Direction, ...]
    locked_direction: Direction | None
    permissions: DevicePermissions
    auxiliary_battery: AuxiliaryBatteryConfig | None


@dataclass(frozen=True, slots=True)
class DisplayConfig:
    unavailable_devices: UnavailableDeviceDisplay = UnavailableDeviceDisplay.HIDE


@dataclass(frozen=True, slots=True)
class DebugConfig:
    raw_capture: bool = False
    capture_directory: str = "/var/log/dbus-wengao/capture"


@dataclass(frozen=True, slots=True)
class DriverConfig:
    config_version: int
    devices: tuple[DeviceConfig, ...]
    display: DisplayConfig
    debug: DebugConfig

    def enabled_devices(self) -> tuple[DeviceConfig, ...]:
        return tuple(device for device in self.devices if device.enabled)

    def device(self, device_id: str) -> DeviceConfig:
        matches = [device for device in self.devices if device.id == device_id]
        if not matches:
            raise ConfigurationError(f"device {device_id!r} is not configured")
        return matches[0]


EnumType = TypeVar("EnumType")


def load_config(path: Path, *, require_ports_exist: bool = False) -> DriverConfig:
    try:
        with path.open("rb") as handle:
            raw = toml_parser.load(handle)
    except (OSError, toml_parser.TOMLDecodeError) as error:
        raise ConfigurationError(f"cannot load configuration {path}: {error}") from error
    return parse_config(raw, require_ports_exist=require_ports_exist)


def parse_config(raw: dict[str, Any], *, require_ports_exist: bool = False) -> DriverConfig:
    _reject_unknown(raw, {"config_version", "devices", "display", "debug"}, "root")
    version = raw.get("config_version")
    if version != CONFIG_VERSION:
        raise ConfigurationError(
            f"unsupported config_version {version!r}; expected {CONFIG_VERSION}"
        )
    raw_devices = raw.get("devices", [])
    if not isinstance(raw_devices, list):
        raise ConfigurationError("devices must be an array of tables")
    devices = tuple(
        _parse_device(cast(dict[str, Any], item), require_ports_exist=require_ports_exist)
        for item in raw_devices
    )
    raw_display = raw.get("display", {})
    if not isinstance(raw_display, dict):
        raise ConfigurationError("display must be a table")
    _reject_unknown(raw_display, {"unavailable_devices"}, "display")
    display = DisplayConfig(
        unavailable_devices=_enum(
            UnavailableDeviceDisplay,
            raw_display.get("unavailable_devices", UnavailableDeviceDisplay.HIDE.value),
            "display.unavailable_devices",
        )
    )
    raw_debug = raw.get("debug", {})
    if not isinstance(raw_debug, dict):
        raise ConfigurationError("debug must be a table")
    _reject_unknown(raw_debug, {"raw_capture", "capture_directory"}, "debug")
    debug = DebugConfig(
        raw_capture=_boolean(raw_debug.get("raw_capture", False), "debug.raw_capture"),
        capture_directory=_string(
            raw_debug.get("capture_directory", "/var/log/dbus-wengao/capture"),
            "debug.capture_directory",
        ),
    )
    config = DriverConfig(CONFIG_VERSION, devices, display, debug)
    _validate_cross_device(config)
    return config


def _parse_device(raw: dict[str, Any], *, require_ports_exist: bool) -> DeviceConfig:
    if not isinstance(raw, dict):
        raise ConfigurationError("each devices entry must be a table")
    allowed_keys = {
        "id",
        "enabled",
        "profile",
        "port",
        "slave_address",
        "system_terminal",
        "device_instance",
        "custom_name",
        "venus_role",
        "control_mode",
        "dvcc_policy",
        "communication_timeout",
        "poll_interval",
        "allowed_directions",
        "locked_direction",
        "permissions",
        "auxiliary_battery",
    }
    _reject_unknown(raw, allowed_keys, "device")
    device_id = _string(raw.get("id"), "device.id")
    if not DEVICE_ID_PATTERN.fullmatch(device_id):
        raise ConfigurationError(f"device.id {device_id!r} must match {DEVICE_ID_PATTERN.pattern}")
    profile_name = _string(raw.get("profile"), f"devices.{device_id}.profile")
    try:
        profile = BUILTIN_PROFILES[profile_name]
    except KeyError as error:
        raise ConfigurationError(
            f"devices.{device_id}.profile is unknown: {profile_name!r}"
        ) from error
    enabled = _boolean(raw.get("enabled", False), f"devices.{device_id}.enabled")
    port = _string(raw.get("port"), f"devices.{device_id}.port")
    if not (port.startswith(STABLE_SERIAL_PREFIX) or port.startswith("/dev/tty")):
        raise ConfigurationError(
            f"devices.{device_id}.port must use {STABLE_SERIAL_PREFIX} or a direct /dev/tty path"
        )
    if enabled and "REPLACE_ME" in port:
        raise ConfigurationError(f"devices.{device_id} is enabled with a placeholder port")
    if enabled and require_ports_exist and not Path(port).exists():
        raise ConfigurationError(f"devices.{device_id}.port does not exist: {port}")
    address = _integer(raw.get("slave_address", 1), f"devices.{device_id}.slave_address")
    if not 1 <= address <= 247:
        raise ConfigurationError(f"devices.{device_id}.slave_address must be in 1..247")
    terminal = _enum(Terminal, raw.get("system_terminal"), f"devices.{device_id}.system_terminal")
    instance = _integer(raw.get("device_instance"), f"devices.{device_id}.device_instance")
    if not 0 <= instance <= MAX_DEVICE_INSTANCE:
        raise ConfigurationError(
            f"devices.{device_id}.device_instance must be in 0..{MAX_DEVICE_INSTANCE}"
        )
    custom_name = _string(raw.get("custom_name"), f"devices.{device_id}.custom_name").strip()
    if not custom_name or len(custom_name) > 64:
        raise ConfigurationError(f"devices.{device_id}.custom_name must contain 1..64 characters")
    role = _enum(
        VenusRole,
        raw.get("venus_role", profile.default_venus_role.value),
        f"devices.{device_id}.venus_role",
    )
    if role not in profile.allowed_venus_roles:
        raise ConfigurationError(
            f"devices.{device_id}.venus_role {role.value!r} is incompatible with {profile.id}"
        )
    control_mode = _enum(
        ControlMode,
        raw.get("control_mode", ControlMode.MONITOR_ONLY.value),
        f"devices.{device_id}.control_mode",
    )
    dvcc = _enum(
        DvccPolicy,
        raw.get("dvcc_policy", DvccPolicy.DISABLED.value),
        f"devices.{device_id}.dvcc_policy",
    )
    timeout = _number(
        raw.get("communication_timeout", 1.0),
        f"devices.{device_id}.communication_timeout",
    )
    if not 0.1 <= timeout <= 10:
        raise ConfigurationError(
            f"devices.{device_id}.communication_timeout must be in 0.1..10 seconds"
        )
    interval = _number(raw.get("poll_interval", 2.0), f"devices.{device_id}.poll_interval")
    if not 0.5 <= interval <= 60:
        raise ConfigurationError(f"devices.{device_id}.poll_interval must be in 0.5..60 seconds")
    directions_raw = raw.get(
        "allowed_directions", [direction.value for direction in profile.default_directions]
    )
    if not isinstance(directions_raw, list):
        raise ConfigurationError(f"devices.{device_id}.allowed_directions must be an array")
    directions = tuple(
        _enum(Direction, value, f"devices.{device_id}.allowed_directions")
        for value in directions_raw
    )
    if len(set(directions)) != len(directions):
        raise ConfigurationError(f"devices.{device_id}.allowed_directions contains duplicates")
    locked_raw = raw.get("locked_direction", "")
    locked = (
        None
        if locked_raw in {None, ""}
        else _enum(Direction, locked_raw, f"devices.{device_id}.locked_direction")
    )
    if profile.direction_must_be_locked:
        if len(directions) != 1 or locked is None or locked != directions[0]:
            raise ConfigurationError(
                f"devices.{device_id} fixed-direction profile requires exactly one allowed "
                "direction and the same locked_direction"
            )
    elif not directions:
        raise ConfigurationError(f"devices.{device_id}.allowed_directions must not be empty")
    if locked is not None and locked not in directions:
        raise ConfigurationError(
            f"devices.{device_id}.locked_direction must be included in allowed_directions"
        )
    raw_permissions = raw.get("permissions", {})
    if not isinstance(raw_permissions, dict):
        raise ConfigurationError(f"devices.{device_id}.permissions must be a table")
    permissions = _parse_permissions(raw_permissions, device_id)
    if control_mode is ControlMode.MONITOR_ONLY and permissions.any_enabled():
        raise ConfigurationError(
            f"devices.{device_id} enables writes while control_mode is monitor-only"
        )
    if profile.direction_must_be_locked and permissions.set_direction:
        raise ConfigurationError(
            f"devices.{device_id} cannot enable direction writes for a fixed-direction profile"
        )
    if dvcc is not DvccPolicy.DISABLED:
        raise ConfigurationError(f"devices.{device_id}.dvcc_policy is not implemented")
    auxiliary_battery = _parse_auxiliary_battery(
        raw.get("auxiliary_battery"),
        device_id=device_id,
        parent_enabled=enabled,
        system_terminal=terminal,
    )
    return DeviceConfig(
        id=device_id,
        enabled=enabled,
        profile=profile,
        port=port,
        slave_address=address,
        system_terminal=terminal,
        device_instance=instance,
        custom_name=custom_name,
        venus_role=role,
        control_mode=control_mode,
        dvcc_policy=dvcc,
        communication_timeout=timeout,
        poll_interval=interval,
        allowed_directions=directions,
        locked_direction=locked,
        permissions=permissions,
        auxiliary_battery=auxiliary_battery,
    )


def _parse_auxiliary_battery(
    raw: object,
    *,
    device_id: str,
    parent_enabled: bool,
    system_terminal: Terminal,
) -> AuxiliaryBatteryConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigurationError(f"devices.{device_id}.auxiliary_battery must be a table")
    context = f"devices.{device_id}.auxiliary_battery"
    _reject_unknown(raw, {"enabled", "terminal", "device_instance", "custom_name"}, context)
    enabled = _boolean(raw.get("enabled", False), f"{context}.enabled")
    terminal = _enum(Terminal, raw.get("terminal"), f"{context}.terminal")
    instance = _integer(raw.get("device_instance"), f"{context}.device_instance")
    if not 0 <= instance <= MAX_DEVICE_INSTANCE:
        raise ConfigurationError(f"{context}.device_instance must be in 0..{MAX_DEVICE_INSTANCE}")
    custom_name = _string(raw.get("custom_name"), f"{context}.custom_name").strip()
    if not custom_name or len(custom_name) > 64:
        raise ConfigurationError(f"{context}.custom_name must contain 1..64 characters")
    if enabled and not parent_enabled:
        raise ConfigurationError(f"{context} cannot be enabled for a disabled device")
    if enabled and terminal is system_terminal:
        raise ConfigurationError(f"{context}.terminal must differ from system_terminal")
    return AuxiliaryBatteryConfig(enabled, terminal, instance, custom_name)


def _parse_permissions(raw: dict[str, Any], device_id: str) -> DevicePermissions:
    names = {field.name for field in fields(DevicePermissions)}
    _reject_unknown(raw, names, f"devices.{device_id}.permissions")
    values = {
        name: _boolean(raw.get(name, False), f"devices.{device_id}.permissions.{name}")
        for name in names
    }
    return DevicePermissions(**values)


def _validate_cross_device(config: DriverConfig) -> None:
    ids: set[str] = set()
    ports: set[str] = set()
    instances: set[tuple[VenusRole, int]] = set()
    auxiliary_battery_instances: set[int] = set()
    for device in config.devices:
        if device.id in ids:
            raise ConfigurationError(f"duplicate device id: {device.id}")
        ids.add(device.id)
        if not device.enabled:
            continue
        if device.port in ports:
            raise ConfigurationError(
                f"serial port is assigned to multiple enabled devices: {device.port}"
            )
        ports.add(device.port)
        key = (device.venus_role, device.device_instance)
        if key in instances:
            raise ConfigurationError(
                f"DeviceInstance {device.device_instance} is duplicated in class "
                f"{device.venus_role.value}"
            )
        instances.add(key)
        auxiliary = device.auxiliary_battery
        if auxiliary is not None and auxiliary.enabled:
            if auxiliary.device_instance in auxiliary_battery_instances:
                raise ConfigurationError(
                    "auxiliary battery DeviceInstance "
                    f"{auxiliary.device_instance} is duplicated in class battery"
                )
            auxiliary_battery_instances.add(auxiliary.device_instance)


def _reject_unknown(raw: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConfigurationError(f"unknown keys in {context}: {', '.join(unknown)}")


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise ConfigurationError(f"{path} must be a string")
    return value


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigurationError(f"{path} must be true or false")
    return value


def _integer(value: object, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError(f"{path} must be an integer")
    return value


def _number(value: object, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigurationError(f"{path} must be a number")
    return float(value)


def _enum(enum_type: type[EnumType], value: object, path: str) -> EnumType:
    try:
        return enum_type(value)  # type: ignore[call-arg]
    except (TypeError, ValueError) as error:
        allowed = ", ".join(item.value for item in enum_type)  # type: ignore[attr-defined]
        raise ConfigurationError(f"{path} must be one of: {allowed}") from error
