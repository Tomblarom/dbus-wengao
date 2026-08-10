"""Role-aware D-Bus publishing independent of the dbus package."""

from __future__ import annotations

import logging
import re
from typing import Protocol

from wengao import __version__
from wengao.config import AuxiliaryBatteryConfig, DeviceConfig
from wengao.errors import WengaoError
from wengao.model import ControlSettings, DeviceIdentity, RealtimeSnapshot, TerminalMeasurements
from wengao.profiles import (
    ControlMode,
    Direction,
    Terminal,
    VenusRole,
    direction_from_operating_mode,
)

PRODUCT_ID_UNREGISTERED = 0xFFFF


class ServiceBackend(Protocol):
    def add_path(
        self,
        path: str,
        value: object,
        description: str = "",
        writeable: bool = False,
        **kwargs: object,
    ) -> object: ...

    def register(self) -> None: ...

    def __setitem__(self, path: str, value: object) -> None: ...


class DeviceController(Protocol):
    def set_remote_enabled(self, enabled: bool) -> ControlSettings: ...

    def set_voltage(self, terminal: Terminal, voltage_v: float) -> ControlSettings: ...

    def set_current(self, terminal: Terminal, current_a: float) -> ControlSettings: ...


def service_name(config: DeviceConfig) -> str:
    suffix = _dbus_safe_suffix(config.id)
    return f"com.victronenergy.{config.venus_role.value}.{suffix}"


def auxiliary_battery_service_name(config: DeviceConfig) -> str:
    auxiliary = config.auxiliary_battery
    if auxiliary is None or not auxiliary.enabled:
        raise ValueError(f"device {config.id!r} has no enabled auxiliary battery")
    suffix = _dbus_safe_suffix(config.id)
    return f"com.victronenergy.battery.wengao_{suffix}_{auxiliary.terminal.value.lower()}"


def _dbus_safe_suffix(value: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if suffix[0].isdigit():
        suffix = f"device_{suffix}"
    return suffix


class VenusPublisher:
    def __init__(
        self,
        service: ServiceBackend,
        config: DeviceConfig,
        identity: DeviceIdentity | None,
        *,
        show_unavailable: bool = False,
        controller: DeviceController | None = None,
    ) -> None:
        self._service = service
        self._config = config
        self._cache: dict[str, object] = {}
        self._dynamic_paths: set[str] = set()
        self._show_unavailable = show_unavailable
        self._controller = controller
        if config.permissions.any_enabled() and controller is None:
            raise ValueError("write-enabled configuration requires a SafeWriteController")
        self._add_mandatory(identity)
        self._add_common_paths(identity, show_unavailable=show_unavailable)
        self._add_role_paths()
        self._service.register()

    def _add_mandatory(self, identity: DeviceIdentity | None) -> None:
        values: dict[str, object] = {
            "/Mgmt/ProcessName": "dbus-wengao",
            "/Mgmt/ProcessVersion": __version__,
            "/Mgmt/Connection": f"Modbus RTU ({self._config.id})",
            "/DeviceInstance": self._config.device_instance,
            "/ProductId": PRODUCT_ID_UNREGISTERED,
            "/ProductName": "Wengao WG-48BC1500M",
            "/FirmwareVersion": identity.firmware_version if identity else None,
            "/HardwareVersion": identity.hardware_version if identity else None,
            "/Connected": int(identity is not None),
        }
        for path, value in values.items():
            self._add(path, value)

    def _add_common_paths(self, identity: DeviceIdentity | None, *, show_unavailable: bool) -> None:
        connected = identity is not None
        communication_error = int(not connected and self._config.alarms.communication)
        communication_alarm = 2 if communication_error else 0
        static: dict[str, object] = {
            "/CustomName": self._config.custom_name,
            "/Serial": identity.serial_number if identity else None,
            "/Mode": 1 if self._config.control_mode is ControlMode.MONITOR_ONLY else None,
            "/State": 0,
            "/ErrorCode": communication_error,
            "/Alarms/Communication": communication_alarm,
            "/Wengao/Model": identity.model if identity else None,
            "/Wengao/ProtocolVersion": identity.protocol_version if identity else None,
            "/WengaoShowUnavailable": int(show_unavailable),
            "/WengaoDisplayOrder": self._config.display_order,
            "/Wengao/Control/WritesEnabled": int(self._config.permissions.any_enabled()),
            "/Wengao/Control/LastResult": "never",
            "/Wengao/Direction": None,
            "/Wengao/DirectionAllowed": None,
            "/Wengao/PowerMode": None,
            "/Wengao/OperatingMode": None,
            "/Wengao/ChargingState": None,
            "/Wengao/FaultBits": None,
            "/Wengao/AlarmBits": None,
            "/Wengao/AccVoltage": None,
            "/Wengao/RmtVoltage": None,
            "/Wengao/TerminalA/Voltage": None,
            "/Wengao/TerminalA/Current": None,
            "/Wengao/TerminalA/Power": None,
            "/Wengao/TerminalB/Voltage": None,
            "/Wengao/TerminalB/Current": None,
            "/Wengao/TerminalB/Power": None,
        }
        runtime_paths = {
            "/Wengao/Direction",
            "/Wengao/DirectionAllowed",
            "/Wengao/PowerMode",
            "/Wengao/OperatingMode",
            "/Wengao/ChargingState",
            "/Wengao/FaultBits",
            "/Wengao/AlarmBits",
            "/Wengao/AccVoltage",
            "/Wengao/RmtVoltage",
            "/Wengao/TerminalA/Voltage",
            "/Wengao/TerminalA/Current",
            "/Wengao/TerminalA/Power",
            "/Wengao/TerminalB/Voltage",
            "/Wengao/TerminalB/Current",
            "/Wengao/TerminalB/Power",
        }
        for path, value in static.items():
            if path == "/Mode":
                self._add(
                    path,
                    value,
                    dynamic=True,
                    writeable=self._can_write_remote(),
                    onchangecallback=self._on_mode_changed,
                )
            else:
                self._add(path, value, dynamic=path in runtime_paths)
        self._add_control_paths()

    def publish_identity(self, identity: DeviceIdentity) -> None:
        self._set("/FirmwareVersion", identity.firmware_version)
        self._set("/HardwareVersion", identity.hardware_version)
        self._set("/Serial", identity.serial_number)
        self._set("/Wengao/Model", identity.model)
        self._set("/Wengao/ProtocolVersion", identity.protocol_version)

    def publish_control(self, settings: ControlSettings) -> None:
        self._set("/Mode", 1 if settings.remote_enabled else 4)
        for terminal, values in (
            (Terminal.A, settings.terminal_a),
            (Terminal.B, settings.terminal_b),
        ):
            prefix = f"/Wengao/Settings/Terminal{terminal.value}"
            self._set(f"{prefix}/Voltage", values.voltage_v)
            self._set(f"{prefix}/Current", values.current_a)
            self._set(f"{prefix}/Power", values.power_w)

    def _add_role_paths(self) -> None:
        role = self._config.venus_role
        for path in ("/Dc/0/Voltage", "/Dc/0/Current", "/Dc/0/Power", "/Dc/0/Temperature"):
            self._add(path, None, dynamic=True)
        if role in {VenusRole.ALTERNATOR, VenusRole.DC_DC}:
            for path in ("/Dc/In/V", "/Dc/In/I", "/Dc/In/P"):
                self._add(path, None, dynamic=True)
        if role is VenusRole.ALTERNATOR:
            self._add("/Settings/BmsPresent", 0)

    def publish(self, snapshot: RealtimeSnapshot) -> None:
        direction = direction_from_operating_mode(snapshot.operating_mode)
        allowed = direction is not None and direction in self._config.allowed_directions
        self._set("/Connected", 1)
        self._set("/WengaoDisplayOrder", self._config.display_order)
        self._set("/Alarms/Communication", 0)
        self._set("/Wengao/Direction", direction.value if direction else None)
        self._set("/Wengao/DirectionAllowed", int(allowed) if direction else None)
        self._set("/Wengao/PowerMode", snapshot.power_mode)
        self._set("/Wengao/OperatingMode", snapshot.operating_mode)
        self._set("/Wengao/ChargingState", snapshot.charging_state)
        self._set("/Wengao/FaultBits", snapshot.fault_bits)
        self._set("/Wengao/AlarmBits", snapshot.alarm_bits)
        self._set("/Wengao/AccVoltage", snapshot.acc_voltage_v)
        self._set("/Wengao/RmtVoltage", snapshot.rmt_voltage_v)
        self._publish_raw_terminal("A", snapshot.terminal_a)
        self._publish_raw_terminal("B", snapshot.terminal_b)
        self._set("/ErrorCode", 0 if snapshot.fault_bits == 0 and allowed else 1)
        self._set("/State", _venus_state(snapshot.charging_state) if allowed else 0)
        if direction is None or direction not in self._config.allowed_directions:
            self._invalidate_role_measurements(keep_voltage=True, snapshot=snapshot)
            return
        if self._config.venus_role is VenusRole.DC_SYSTEM:
            self._publish_dc_system(snapshot, direction)
        elif self._config.venus_role is VenusRole.ALTERNATOR:
            self._publish_alternator(snapshot, direction)
        else:
            self._publish_dc_dc(snapshot, direction)

    def mark_disconnected(self) -> None:
        self._set("/Connected", 0)
        communication_error = int(self._config.alarms.communication)
        self._set("/Alarms/Communication", 2 if communication_error else 0)
        self._set("/State", 0)
        self._set("/ErrorCode", communication_error)
        if not self._show_unavailable:
            self._set("/WengaoDisplayOrder", None)
        for path in self._dynamic_paths:
            if path not in {"/State", "/ErrorCode"}:
                self._set(path, None)

    def _add_control_paths(self) -> None:
        destinations = {
            Terminal.B if direction is Direction.A_TO_B else Terminal.A
            for direction in self._config.allowed_directions
        }
        for terminal in (Terminal.A, Terminal.B):
            prefix = f"/Wengao/Settings/Terminal{terminal.value}"
            can_write_voltage = (
                terminal in destinations
                and self._can_write()
                and self._config.permissions.set_voltage
            )
            can_write_current = (
                terminal in destinations
                and self._can_write()
                and self._config.permissions.set_current
            )
            self._add(
                f"{prefix}/Voltage",
                None,
                dynamic=True,
                writeable=can_write_voltage,
                onchangecallback=(
                    lambda path, value, selected=terminal: self._on_setpoint_changed(
                        path, value, selected, "voltage"
                    )
                ),
            )
            self._add(
                f"{prefix}/Current",
                None,
                dynamic=True,
                writeable=can_write_current,
                onchangecallback=(
                    lambda path, value, selected=terminal: self._on_setpoint_changed(
                        path, value, selected, "current"
                    )
                ),
            )
            self._add(f"{prefix}/Power", None, dynamic=True)

    def _can_write(self) -> bool:
        return (
            self._config.control_mode is ControlMode.EXTERNAL_DBUS
            and self._controller is not None
        )

    def _can_write_remote(self) -> bool:
        return self._can_write() and self._config.permissions.remote_on_off

    def _on_mode_changed(self, _path: str, value: object) -> bool:
        if not self._can_write_remote() or self._controller is None:
            return self._write_rejected("remote on/off is not permitted")
        if isinstance(value, bool) or not isinstance(value, int) or value not in {1, 4}:
            return self._write_rejected("Mode accepts only 1 (on) or 4 (off)")
        try:
            verified = self._controller.set_remote_enabled(value == 1)
        except (OSError, ValueError, WengaoError) as error:
            return self._write_rejected(str(error))
        self.publish_control(verified)
        self._set("/Wengao/Control/LastResult", "ok")
        return True

    def _on_setpoint_changed(
        self, _path: str, value: object, terminal: Terminal, kind: str
    ) -> bool:
        if not self._can_write() or self._controller is None:
            return self._write_rejected("external D-Bus control is disabled")
        try:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{kind} must be numeric")
            verified = (
                self._controller.set_voltage(terminal, float(value))
                if kind == "voltage"
                else self._controller.set_current(terminal, float(value))
            )
        except (OSError, ValueError, WengaoError) as error:
            return self._write_rejected(str(error))
        self.publish_control(verified)
        self._set("/Wengao/Control/LastResult", "ok")
        return True

    def _write_rejected(self, reason: str) -> bool:
        logging.warning("D-Bus write rejected for %s: %s", self._config.id, reason)
        self._set("/Wengao/Control/LastResult", f"rejected: {reason}")
        return False

    def _publish_dc_system(self, snapshot: RealtimeSnapshot, direction: Direction) -> None:
        terminal = _system_measurements(snapshot, self._config.system_terminal)
        sign = _system_outward_sign(direction, self._config.system_terminal)
        self._set("/Dc/0/Voltage", terminal.voltage_v)
        self._set("/Dc/0/Current", sign * terminal.current_a)
        self._set("/Dc/0/Power", sign * terminal.power_w)
        self._set("/Dc/0/Temperature", snapshot.ambient_temperature_c)

    def _publish_alternator(self, snapshot: RealtimeSnapshot, direction: Direction) -> None:
        output = _system_measurements(snapshot, self._config.system_terminal)
        input_measurements = _other_measurements(snapshot, self._config.system_terminal)
        charge_sign = -_system_outward_sign(direction, self._config.system_terminal)
        self._set("/Dc/0/Voltage", output.voltage_v)
        self._set("/Dc/0/Current", charge_sign * output.current_a)
        self._set("/Dc/0/Power", charge_sign * output.power_w)
        self._set("/Dc/0/Temperature", snapshot.ambient_temperature_c)
        self._set("/Dc/In/V", input_measurements.voltage_v)
        self._set("/Dc/In/I", input_measurements.current_a)
        self._set("/Dc/In/P", input_measurements.power_w)

    def _publish_dc_dc(self, snapshot: RealtimeSnapshot, direction: Direction) -> None:
        source, destination = _flow_measurements(snapshot, direction)
        self._set("/Dc/0/Voltage", destination.voltage_v)
        self._set("/Dc/0/Current", destination.current_a)
        self._set("/Dc/0/Power", destination.power_w)
        self._set("/Dc/0/Temperature", snapshot.ambient_temperature_c)
        self._set("/Dc/In/V", source.voltage_v)
        self._set("/Dc/In/I", source.current_a)
        self._set("/Dc/In/P", source.power_w)

    def _invalidate_role_measurements(
        self, *, keep_voltage: bool, snapshot: RealtimeSnapshot
    ) -> None:
        system = _system_measurements(snapshot, self._config.system_terminal)
        self._set("/Dc/0/Voltage", system.voltage_v if keep_voltage else None)
        for path in ("/Dc/0/Current", "/Dc/0/Power", "/Dc/0/Temperature"):
            self._set(path, None)
        if self._config.venus_role in {VenusRole.ALTERNATOR, VenusRole.DC_DC}:
            for path in ("/Dc/In/V", "/Dc/In/I", "/Dc/In/P"):
                self._set(path, None)

    def _publish_raw_terminal(self, terminal: str, values: TerminalMeasurements) -> None:
        self._set(f"/Wengao/Terminal{terminal}/Voltage", values.voltage_v)
        self._set(f"/Wengao/Terminal{terminal}/Current", values.current_a)
        self._set(f"/Wengao/Terminal{terminal}/Power", values.power_w)

    def _add(
        self,
        path: str,
        value: object,
        *,
        dynamic: bool = False,
        writeable: bool = False,
        onchangecallback: object | None = None,
    ) -> None:
        if writeable:
            self._service.add_path(
                path,
                value,
                writeable=True,
                onchangecallback=onchangecallback,
            )
        else:
            self._service.add_path(path, value, writeable=False)
        self._cache[path] = value
        if dynamic:
            self._dynamic_paths.add(path)

    def _set(self, path: str, value: object) -> None:
        if self._cache.get(path) == value:
            return
        self._service[path] = value
        self._cache[path] = value


class AuxiliaryBatteryPublisher:
    """Publish one converter terminal as a non-BMS battery monitor."""

    def __init__(
        self,
        service: ServiceBackend,
        config: DeviceConfig,
        identity: DeviceIdentity | None,
    ) -> None:
        auxiliary = config.auxiliary_battery
        if auxiliary is None or not auxiliary.enabled:
            raise ValueError(f"device {config.id!r} has no enabled auxiliary battery")
        self._service = service
        self._device_config = config
        self._config: AuxiliaryBatteryConfig = auxiliary
        self._cache: dict[str, object] = {}
        connected = identity is not None
        communication_alarm = 2 if not connected and config.alarms.communication else 0
        serial = _auxiliary_serial(identity, auxiliary.terminal)
        values: dict[str, object] = {
            "/Mgmt/ProcessName": "dbus-wengao",
            "/Mgmt/ProcessVersion": __version__,
            "/Mgmt/Connection": f"Modbus RTU ({config.id}, terminal {auxiliary.terminal.value})",
            "/DeviceInstance": auxiliary.device_instance,
            "/ProductId": PRODUCT_ID_UNREGISTERED,
            "/ProductName": "Wengao auxiliary battery monitor",
            "/FirmwareVersion": identity.firmware_version if identity else None,
            "/HardwareVersion": identity.hardware_version if identity else None,
            "/Connected": int(connected),
            "/CustomName": auxiliary.custom_name,
            "/Serial": serial,
            "/Dc/0/Voltage": None,
            "/Dc/0/Current": None,
            "/Dc/0/Power": None,
            "/Dc/0/Temperature": None,
            "/Soc": None,
            "/Alarms/Communication": communication_alarm,
            "/Wengao/SourceDevice": config.id,
            "/Wengao/Terminal": auxiliary.terminal.value,
        }
        for path, value in values.items():
            self._add(path, value)
        self._service.register()

    def publish_identity(self, identity: DeviceIdentity) -> None:
        self._set("/FirmwareVersion", identity.firmware_version)
        self._set("/HardwareVersion", identity.hardware_version)
        self._set("/Serial", _auxiliary_serial(identity, self._config.terminal))

    def publish(self, snapshot: RealtimeSnapshot) -> None:
        measurements = _system_measurements(snapshot, self._config.terminal)
        direction = direction_from_operating_mode(snapshot.operating_mode)
        self._set("/Connected", 1)
        self._set("/Alarms/Communication", 0)
        self._set("/Dc/0/Voltage", measurements.voltage_v)
        self._set("/Dc/0/Temperature", snapshot.ambient_temperature_c)
        if direction is None:
            self._set("/Dc/0/Current", None)
            self._set("/Dc/0/Power", None)
            return
        charge_sign = -_system_outward_sign(direction, self._config.terminal)
        self._set("/Dc/0/Current", charge_sign * measurements.current_a)
        self._set("/Dc/0/Power", charge_sign * measurements.power_w)

    def mark_disconnected(self) -> None:
        self._set("/Connected", 0)
        self._set("/Alarms/Communication", 2 if self._device_config.alarms.communication else 0)
        for path in (
            "/Dc/0/Voltage",
            "/Dc/0/Current",
            "/Dc/0/Power",
            "/Dc/0/Temperature",
        ):
            self._set(path, None)

    def _add(self, path: str, value: object) -> None:
        self._service.add_path(path, value, writeable=False)
        self._cache[path] = value

    def _set(self, path: str, value: object) -> None:
        if self._cache.get(path) == value:
            return
        self._service[path] = value
        self._cache[path] = value


def _auxiliary_serial(identity: DeviceIdentity | None, terminal: Terminal) -> str | None:
    if identity is None:
        return None
    return f"{identity.serial_number}-{terminal.value}"


def _system_measurements(
    snapshot: RealtimeSnapshot, system_terminal: Terminal
) -> TerminalMeasurements:
    return snapshot.terminal_a if system_terminal is Terminal.A else snapshot.terminal_b


def _other_measurements(
    snapshot: RealtimeSnapshot, system_terminal: Terminal
) -> TerminalMeasurements:
    return snapshot.terminal_b if system_terminal is Terminal.A else snapshot.terminal_a


def _flow_measurements(
    snapshot: RealtimeSnapshot, direction: Direction
) -> tuple[TerminalMeasurements, TerminalMeasurements]:
    if direction is Direction.A_TO_B:
        return snapshot.terminal_a, snapshot.terminal_b
    return snapshot.terminal_b, snapshot.terminal_a


def _system_outward_sign(direction: Direction, system_terminal: Terminal) -> int:
    leaves_system = (direction is Direction.A_TO_B and system_terminal is Terminal.A) or (
        direction is Direction.B_TO_A and system_terminal is Terminal.B
    )
    return 1 if leaves_system else -1


def _venus_state(charging_state: int) -> int:
    # Victron: 0 Off, 3 Bulk, 4 Absorption, 5 Float, 11 Power supply.
    return {0: 11, 1: 3, 2: 3, 3: 4, 4: 5, 5: 0}.get(charging_state, 0)
