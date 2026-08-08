"""Role-aware, read-only D-Bus publishing independent of the dbus package."""

from __future__ import annotations

import re
from typing import Protocol

from wengao import __version__
from wengao.config import DeviceConfig
from wengao.model import DeviceIdentity, RealtimeSnapshot, TerminalMeasurements
from wengao.profiles import Direction, Terminal, VenusRole, direction_from_operating_mode

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


def service_name(config: DeviceConfig) -> str:
    suffix = re.sub(r"[^A-Za-z0-9_]", "_", config.id)
    if suffix[0].isdigit():
        suffix = f"device_{suffix}"
    return f"com.victronenergy.{config.venus_role.value}.{suffix}"


class VenusPublisher:
    def __init__(
        self,
        service: ServiceBackend,
        config: DeviceConfig,
        identity: DeviceIdentity,
    ) -> None:
        self._service = service
        self._config = config
        self._cache: dict[str, object] = {}
        self._dynamic_paths: set[str] = set()
        self._add_mandatory(identity)
        self._add_common_paths(identity)
        self._add_role_paths()
        self._service.register()

    def _add_mandatory(self, identity: DeviceIdentity) -> None:
        values: dict[str, object] = {
            "/Mgmt/ProcessName": "dbus-wengao",
            "/Mgmt/ProcessVersion": __version__,
            "/Mgmt/Connection": f"Modbus RTU ({self._config.id})",
            "/DeviceInstance": self._config.device_instance,
            "/ProductId": PRODUCT_ID_UNREGISTERED,
            "/ProductName": "Wengao WG-48BC1500M",
            "/FirmwareVersion": identity.firmware_version,
            "/HardwareVersion": identity.hardware_version,
            "/Connected": 1,
        }
        for path, value in values.items():
            self._add(path, value)

    def _add_common_paths(self, identity: DeviceIdentity) -> None:
        static: dict[str, object] = {
            "/CustomName": self._config.custom_name,
            "/Serial": identity.serial_number,
            "/Mode": 1,
            "/State": 0,
            "/ErrorCode": 0,
            "/Alarms/Communication": 0,
            "/Wengao/Model": identity.model,
            "/Wengao/ProtocolVersion": identity.protocol_version,
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
        for path, value in static.items():
            self._add(path, value, dynamic=value is None or path in {"/State", "/ErrorCode"})

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
        self._set("/Alarms/Communication", 2)
        self._set("/State", 0)
        self._set("/ErrorCode", 1)
        for path in self._dynamic_paths:
            if path not in {"/State", "/ErrorCode"}:
                self._set(path, None)

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

    def _add(self, path: str, value: object, *, dynamic: bool = False) -> None:
        self._service.add_path(path, value, writeable=False)
        self._cache[path] = value
        if dynamic:
            self._dynamic_paths.add(path)

    def _set(self, path: str, value: object) -> None:
        if self._cache.get(path) == value:
            return
        self._service[path] = value
        self._cache[path] = value


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
