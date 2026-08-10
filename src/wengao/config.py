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
HARDWARE_VOLTAGE_MIN = 10.0
HARDWARE_VOLTAGE_MAX = 60.0
HARDWARE_CURRENT_MAX = {Terminal.A: 100.0, Terminal.B: 25.0}


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
class AlarmConfig:
    communication: bool = True


@dataclass(frozen=True, slots=True)
class AuxiliaryBatteryConfig:
    enabled: bool
    terminal: Terminal
    device_instance: int
    custom_name: str


@dataclass(frozen=True, slots=True)
class WriteRange:
    minimum: float
    maximum: float

    def contains(self, value: float) -> bool:
        return self.minimum <= value <= self.maximum


@dataclass(frozen=True, slots=True)
class WriteLimits:
    minimum_interval: float
    terminal_a_voltage: WriteRange | None
    terminal_a_current: WriteRange | None
    terminal_b_voltage: WriteRange | None
    terminal_b_current: WriteRange | None

    def voltage(self, terminal: Terminal) -> WriteRange | None:
        return self.terminal_a_voltage if terminal is Terminal.A else self.terminal_b_voltage

    def current(self, terminal: Terminal) -> WriteRange | None:
        return self.terminal_a_current if terminal is Terminal.A else self.terminal_b_current


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
    alarms: AlarmConfig
    auxiliary_battery: AuxiliaryBatteryConfig | None
    write_limits: WriteLimits
    display_order: int = 0


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
        _parse_device(
            cast(dict[str, Any], item),
            display_order=index,
            require_ports_exist=require_ports_exist,
        )
        for index, item in enumerate(raw_devices)
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


def _parse_device(
    raw: dict[str, Any], *, display_order: int, require_ports_exist: bool
) -> DeviceConfig:
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
        "alarms",
        "auxiliary_battery",
        "write_limits",
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
    alarms = _parse_alarm_config(raw.get("alarms"), device_id=device_id)
    if control_mode is ControlMode.MONITOR_ONLY and permissions.any_enabled():
        raise ConfigurationError(
            f"devices.{device_id} enables writes while control_mode is monitor-only"
        )
    if profile.direction_must_be_locked and permissions.set_direction:
        raise ConfigurationError(
            f"devices.{device_id} cannot enable direction writes for a fixed-direction profile"
        )
    unsupported_permissions = {
        name
        for name in (
            "set_direction",
            "set_mode",
            "set_protection_limits",
            "calibration",
            "factory_reset",
        )
        if getattr(permissions, name)
    }
    if unsupported_permissions:
        raise ConfigurationError(
            f"devices.{device_id} enables unimplemented write permissions: "
            + ", ".join(sorted(unsupported_permissions))
        )
    write_limits = _parse_write_limits(raw.get("write_limits"), device_id=device_id)
    _validate_write_configuration(
        device_id=device_id,
        control_mode=control_mode,
        permissions=permissions,
        directions=directions,
        write_limits=write_limits,
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
        alarms=alarms,
        auxiliary_battery=auxiliary_battery,
        write_limits=write_limits,
        display_order=display_order,
    )


def _parse_write_limits(raw: object, *, device_id: str) -> WriteLimits:
    context = f"devices.{device_id}.write_limits"
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigurationError(f"{context} must be a table")
    keys = {
        "minimum_interval",
        "terminal_a_voltage",
        "terminal_a_current",
        "terminal_b_voltage",
        "terminal_b_current",
    }
    _reject_unknown(raw, keys, context)
    interval = _number(raw.get("minimum_interval", 5.0), f"{context}.minimum_interval")
    if not 1.0 <= interval <= 3600.0:
        raise ConfigurationError(f"{context}.minimum_interval must be in 1..3600 seconds")
    return WriteLimits(
        minimum_interval=interval,
        terminal_a_voltage=_parse_write_range(
            raw.get("terminal_a_voltage"), f"{context}.terminal_a_voltage"
        ),
        terminal_a_current=_parse_write_range(
            raw.get("terminal_a_current"), f"{context}.terminal_a_current"
        ),
        terminal_b_voltage=_parse_write_range(
            raw.get("terminal_b_voltage"), f"{context}.terminal_b_voltage"
        ),
        terminal_b_current=_parse_write_range(
            raw.get("terminal_b_current"), f"{context}.terminal_b_current"
        ),
    )


def _parse_write_range(raw: object, path: str) -> WriteRange | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) != 2:
        raise ConfigurationError(f"{path} must be [minimum, maximum]")
    minimum = _number(raw[0], f"{path}[0]")
    maximum = _number(raw[1], f"{path}[1]")
    if minimum > maximum:
        raise ConfigurationError(f"{path} minimum must not exceed maximum")
    return WriteRange(minimum, maximum)


def _validate_write_configuration(
    *,
    device_id: str,
    control_mode: ControlMode,
    permissions: DevicePermissions,
    directions: tuple[Direction, ...],
    write_limits: WriteLimits,
) -> None:
    if permissions.any_enabled() and control_mode is not ControlMode.EXTERNAL_DBUS:
        raise ConfigurationError(
            f"devices.{device_id} write permissions require control_mode = 'external-dbus'"
        )
    for terminal in (Terminal.A, Terminal.B):
        voltage = write_limits.voltage(terminal)
        current = write_limits.current(terminal)
        prefix = f"devices.{device_id}.write_limits.terminal_{terminal.value.lower()}"
        if voltage is not None and not (
            HARDWARE_VOLTAGE_MIN <= voltage.minimum <= voltage.maximum <= HARDWARE_VOLTAGE_MAX
        ):
            raise ConfigurationError(
                f"{prefix}_voltage must stay within "
                f"{HARDWARE_VOLTAGE_MIN:g}..{HARDWARE_VOLTAGE_MAX:g} V"
            )
        terminal_current_max = HARDWARE_CURRENT_MAX[terminal]
        if current is not None and not (
            1.0 <= current.minimum <= current.maximum <= terminal_current_max
        ):
            raise ConfigurationError(
                f"{prefix}_current must stay within 1..{terminal_current_max:g} A"
            )

    destinations = {
        Terminal.B if direction is Direction.A_TO_B else Terminal.A for direction in directions
    }
    for terminal in destinations:
        voltage = write_limits.voltage(terminal)
        current = write_limits.current(terminal)
        prefix = f"devices.{device_id}.write_limits.terminal_{terminal.value.lower()}"
        if permissions.set_voltage and voltage is None:
            raise ConfigurationError(f"{prefix}_voltage is required when set_voltage is enabled")
        if permissions.set_current and current is None:
            raise ConfigurationError(f"{prefix}_current is required when set_current is enabled")


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


def _parse_alarm_config(raw: object, *, device_id: str) -> AlarmConfig:
    context = f"devices.{device_id}.alarms"
    if raw is None:
        return AlarmConfig()
    if not isinstance(raw, dict):
        raise ConfigurationError(f"{context} must be a table")
    _reject_unknown(raw, {"communication"}, context)
    return AlarmConfig(
        communication=_boolean(raw.get("communication", True), f"{context}.communication")
    )


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
