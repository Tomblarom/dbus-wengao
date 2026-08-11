from __future__ import annotations

import math
from typing import Any

from wengao.config import DeviceConfig, parse_config
from wengao.model import (
    ControlSettings,
    DeviceIdentity,
    RealtimeSnapshot,
    TerminalMeasurements,
    TerminalSetpoints,
)
from wengao.profiles import Terminal
from wengao.venus.publisher import (
    AuxiliaryBatteryPublisher,
    VenusPublisher,
    auxiliary_battery_service_name,
    service_name,
)


class FakeService:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.events: list[tuple[str, str, object]] = []
        self.set_count = 0
        self.writeable: dict[str, bool] = {}
        self.callbacks: dict[str, object] = {}

    def add_path(
        self,
        path: str,
        value: object,
        description: str = "",
        writeable: bool = False,
        **kwargs: object,
    ) -> object:
        self.values[path] = value
        self.writeable[path] = writeable
        if "onchangecallback" in kwargs:
            self.callbacks[path] = kwargs["onchangecallback"]
        self.events.append(("add", path, value))
        return object()

    def register(self) -> None:
        self.events.append(("register", "", ""))

    def __setitem__(self, path: str, value: object) -> None:
        self.values[path] = value
        self.set_count += 1
        self.events.append(("set", path, value))


def device_config(
    *,
    role: str = "dcsystem",
    system_terminal: str = "B",
    profile: str = "bidirectional-battery-link",
    directions: list[str] | None = None,
    locked: str = "",
    device_id: str = "device-1",
    auxiliary_battery: dict[str, object] | None = None,
    control_mode: str = "monitor-only",
    permissions: dict[str, bool] | None = None,
    write_limits: dict[str, object] | None = None,
    alarms: dict[str, bool] | None = None,
) -> DeviceConfig:
    if directions is None:
        directions = ["A-to-B", "B-to-A"]
    raw: dict[str, Any] = {
        "config_version": 1,
        "devices": [
            {
                "id": device_id,
                "enabled": True,
                "profile": profile,
                "port": "/dev/serial/by-id/synthetic",
                "slave_address": 1,
                "system_terminal": system_terminal,
                "device_instance": 40,
                "custom_name": "Wengao DC-DC",
                "venus_role": role,
                "control_mode": control_mode,
                "dvcc_policy": "disabled",
                "allowed_directions": directions,
                "locked_direction": locked,
                "permissions": permissions or {},
                **({"alarms": alarms} if alarms is not None else {}),
                **({"write_limits": write_limits} if write_limits is not None else {}),
                **(
                    {"auxiliary_battery": auxiliary_battery}
                    if auxiliary_battery is not None
                    else {}
                ),
            }
        ],
    }
    return parse_config(raw).devices[0]


def identity() -> DeviceIdentity:
    return DeviceIdentity("V101", "V103", "V201", "PRIVATE-SERIAL", "WG-BC1500M", 1, 0)


def snapshot(*, mode: int = 4, charging_state: int = 2) -> RealtimeSnapshot:
    registers = (0,) * 16
    return RealtimeSnapshot(
        terminal_a=TerminalMeasurements(55.65, 0.84, 47),
        terminal_b=TerminalMeasurements(12.50, 3.71, 46),
        temperature_t1_c=44,
        temperature_t2_c=43,
        power_mode=2,
        operating_mode=mode,
        fault_bits=0,
        alarm_bits=0,
        acc_voltage_v=56.11,
        rmt_voltage_v=0.19,
        ambient_temperature_c=44,
        charging_state=charging_state,
        raw_registers=registers,
    )


def create_publisher(config: DeviceConfig) -> tuple[FakeService, VenusPublisher]:
    service = FakeService()
    publisher = VenusPublisher(service, config, identity())
    return service, publisher


def test_paths_are_added_before_service_registration() -> None:
    service, _publisher = create_publisher(device_config())
    assert service.events[-1][0] == "register"
    assert "/Connected" in service.values
    assert "/Dc/0/Power" in service.values
    assert service.values["/Wengao/SystemTerminal"] == "B"
    assert not any(path.startswith("/Link/") for path in service.values)
    assert not any(service.writeable.values())


def test_unavailable_placeholder_is_explicit_and_contains_no_false_measurement() -> None:
    service = FakeService()
    publisher = VenusPublisher(service, device_config(), None, show_unavailable=True)
    assert service.events[-1][0] == "register"
    assert service.values["/Connected"] == 0
    assert service.values["/Alarms/Communication"] == 2
    assert service.values["/WengaoShowUnavailable"] == 1
    assert service.values["/Wengao/SystemTerminal"] == "B"
    assert service.values["/Dc/0/Power"] is None
    publisher.publish_identity(identity())
    assert service.values["/Serial"] == "PRIVATE-SERIAL"
    publisher.mark_disconnected()
    assert service.values["/Serial"] == "PRIVATE-SERIAL"


def test_optional_unavailable_device_suppresses_only_communication_faults() -> None:
    config = device_config(
        alarms={"communication": False},
        auxiliary_battery={
            "enabled": True,
            "terminal": "A",
            "device_instance": 80,
            "custom_name": "Auxiliary battery",
        },
    )
    service = FakeService()
    publisher = VenusPublisher(service, config, None, show_unavailable=True)
    assert service.values["/Connected"] == 0
    assert service.values["/ErrorCode"] == 0
    assert service.values["/Alarms/Communication"] == 0
    publisher.mark_disconnected()
    assert service.values["/Connected"] == 0
    assert service.values["/ErrorCode"] == 0
    assert service.values["/Alarms/Communication"] == 0

    auxiliary_service = FakeService()
    auxiliary = AuxiliaryBatteryPublisher(auxiliary_service, config, None)
    assert auxiliary_service.values["/Connected"] == 0
    assert auxiliary_service.values["/Alarms/Communication"] == 0
    auxiliary.mark_disconnected()
    assert auxiliary_service.values["/Alarms/Communication"] == 0


def test_service_name_uses_role_and_dbus_safe_device_id() -> None:
    assert service_name(device_config(device_id="rear-converter")) == (
        "com.victronenergy.dcsystem.rear_converter"
    )


def test_auxiliary_battery_service_name_is_separate_and_dbus_safe() -> None:
    config = device_config(
        device_id="vehicle-link",
        auxiliary_battery={
            "enabled": True,
            "terminal": "A",
            "device_instance": 80,
            "custom_name": "Auxiliary battery",
        },
    )
    assert auxiliary_battery_service_name(config) == (
        "com.victronenergy.battery.wengao_vehicle_link_a"
    )


def test_auxiliary_battery_zero_policy_stays_visible_without_a_false_voltage() -> None:
    config = device_config(
        auxiliary_battery={
            "enabled": True,
            "terminal": "A",
            "device_instance": 80,
            "custom_name": "Auxiliary battery",
        },
    )
    service = FakeService()
    publisher = AuxiliaryBatteryPublisher(service, config, None, show_unavailable=True)
    assert service.values["/Connected"] == 0
    assert math.isnan(service.values["/Dc/0/Voltage"])

    writes_before = service.set_count
    publisher.mark_disconnected()
    assert service.set_count == writes_before

    publisher.publish(snapshot(mode=4))
    assert service.values["/Dc/0/Voltage"] == 55.65
    publisher.mark_disconnected()
    assert math.isnan(service.values["/Dc/0/Voltage"])
    assert service.values["/Dc/0/Current"] is None


def test_dc_system_sign_is_positive_when_power_leaves_system_terminal() -> None:
    service, publisher = create_publisher(device_config(system_terminal="A"))
    publisher.publish(snapshot(mode=4))
    assert service.values["/Dc/0/Voltage"] == 55.65
    assert service.values["/Dc/0/Current"] == 0.84
    assert service.values["/Dc/0/Power"] == 47


def test_terminal_currents_are_positive_for_charge_and_negative_for_discharge() -> None:
    service, publisher = create_publisher(device_config())

    publisher.publish(snapshot(mode=4))
    assert service.values["/Wengao/TerminalA/Current"] == 0.84
    assert service.values["/Wengao/TerminalB/Current"] == 3.71
    assert service.values["/Wengao/TerminalA/SignedCurrent"] == -0.84
    assert service.values["/Wengao/TerminalB/SignedCurrent"] == 3.71

    publisher.publish(snapshot(mode=5))
    assert service.values["/Wengao/TerminalA/SignedCurrent"] == 0.84
    assert service.values["/Wengao/TerminalB/SignedCurrent"] == -3.71


def test_dc_system_sign_is_negative_when_power_enters_system_terminal() -> None:
    service, publisher = create_publisher(device_config(system_terminal="B"))
    publisher.publish(snapshot(mode=4))
    assert service.values["/Dc/0/Voltage"] == 12.5
    assert service.values["/Dc/0/Current"] == -3.71
    assert service.values["/Dc/0/Power"] == -46


def test_alternator_sign_is_positive_when_charging_system_terminal() -> None:
    config = device_config(role="alternator", profile="vehicle-battery-link", system_terminal="B")
    service, publisher = create_publisher(config)
    publisher.publish(snapshot(mode=4))
    assert service.values["/Dc/0/Current"] == 3.71
    assert service.values["/Dc/0/Power"] == 46
    assert service.values["/Dc/In/V"] == 55.65
    assert service.values["/Dc/In/I"] == 0.84
    assert service.values["/Wengao/DcLoadPower"] == 0
    assert service.values["/Settings/BmsPresent"] == 0
    assert not any(path.startswith("/Link/") for path in service.values)


def test_alternator_service_stays_stable_and_power_is_negative_in_reverse() -> None:
    config = device_config(role="alternator", profile="vehicle-battery-link", system_terminal="B")
    service, publisher = create_publisher(config)
    publisher.publish(snapshot(mode=5))
    assert service_name(config) == "com.victronenergy.alternator.device_1"
    assert service.values["/Dc/0/Current"] == -3.71
    assert service.values["/Dc/0/Power"] == -46
    assert service.values["/Wengao/DcLoadPower"] == 46


def test_fixed_dc_dc_uses_physical_source_and_destination() -> None:
    config = device_config(
        role="dcdc",
        profile="fixed-direction-dc-converter",
        directions=["A-to-B"],
        locked="A-to-B",
    )
    service, publisher = create_publisher(config)
    publisher.publish(snapshot(mode=4))
    assert service.values["/Dc/In/V"] == 55.65
    assert service.values["/Dc/In/I"] == 0.84
    assert service.values["/Dc/0/Voltage"] == 12.5
    assert service.values["/Dc/0/Current"] == 3.71


def test_fixed_dc_system_reports_consumption_from_system_terminal() -> None:
    config = device_config(
        role="dcsystem",
        profile="fixed-direction-dc-converter",
        system_terminal="A",
        directions=["A-to-B"],
        locked="A-to-B",
    )
    service, publisher = create_publisher(config)
    publisher.publish(snapshot(mode=4))
    assert service.values["/Dc/0/Voltage"] == 55.65
    assert service.values["/Dc/0/Current"] == 0.84
    assert service.values["/Dc/0/Power"] == 47


def test_disallowed_direction_invalidates_power_and_current() -> None:
    config = device_config(
        role="dcdc",
        profile="fixed-direction-dc-converter",
        directions=["B-to-A"],
        locked="B-to-A",
    )
    service, publisher = create_publisher(config)
    publisher.publish(snapshot(mode=4))
    assert service.values["/Wengao/Direction"] == "A-to-B"
    assert service.values["/Wengao/DirectionAllowed"] == 0
    assert service.values["/Dc/0/Current"] is None
    assert service.values["/Dc/0/Power"] is None
    assert service.values["/ErrorCode"] == 1


def test_unknown_direction_is_not_assumed() -> None:
    service, publisher = create_publisher(device_config())
    publisher.publish(snapshot(mode=99))
    assert service.values["/Wengao/Direction"] is None
    assert service.values["/Wengao/DirectionAllowed"] is None
    assert service.values["/Dc/0/Current"] is None
    assert service.values["/Wengao/TerminalA/SignedCurrent"] is None
    assert service.values["/Wengao/TerminalB/SignedCurrent"] is None


def test_disconnect_invalidates_measurements_and_marks_alarm() -> None:
    service, publisher = create_publisher(device_config())
    publisher.publish(snapshot())
    publisher.mark_disconnected()
    assert service.values["/Connected"] == 0
    assert service.values["/Alarms/Communication"] == 2
    assert service.values["/Dc/0/Voltage"] is None
    assert service.values["/Wengao/TerminalA/Voltage"] is None
    assert service.values["/Wengao/TerminalA/SignedCurrent"] is None
    assert service.values["/Wengao/TerminalB/SignedCurrent"] is None
    assert service.values["/Wengao/DcLoadPower"] is None
    assert service.values["/State"] == 0


def test_redundant_snapshot_does_not_repeat_dbus_writes() -> None:
    service, publisher = create_publisher(device_config())
    publisher.publish(snapshot())
    first_count = service.set_count
    publisher.publish(snapshot())
    assert service.set_count == first_count


def test_unknown_charging_state_is_preserved_raw_but_not_mapped() -> None:
    service, publisher = create_publisher(device_config())
    publisher.publish(snapshot(charging_state=6))
    assert service.values["/Wengao/ChargingState"] == 6


class FakeController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.settings = ControlSettings(
            True,
            TerminalSetpoints(14.4, 50.0, 720),
            TerminalSetpoints(54.0, 20.0, 1080),
        )

    def set_remote_enabled(self, enabled: bool) -> ControlSettings:
        self.calls.append(("remote", enabled))
        return self.settings

    def set_voltage(self, terminal: Terminal, value: float) -> ControlSettings:
        self.calls.append((f"{terminal.value}-voltage", value))
        return self.settings

    def set_current(self, terminal: Terminal, value: float) -> ControlSettings:
        self.calls.append((f"{terminal.value}-current", value))
        return self.settings


def test_external_control_exposes_only_permitted_destination_paths() -> None:
    config = device_config(
        role="dcdc",
        profile="fixed-direction-dc-converter",
        system_terminal="A",
        directions=["A-to-B"],
        locked="A-to-B",
        control_mode="external-dbus",
        permissions={"remote_on_off": True, "set_voltage": True, "set_current": True},
        write_limits={
            "terminal_b_voltage": [48.0, 58.4],
            "terminal_b_current": [1.0, 25.0],
        },
    )
    service = FakeService()
    controller = FakeController()
    VenusPublisher(service, config, identity(), controller=controller)
    assert service.writeable["/Mode"] is True
    assert service.writeable["/Wengao/Settings/TerminalA/Voltage"] is False
    assert service.writeable["/Wengao/Settings/TerminalB/Voltage"] is True
    callback = service.callbacks["/Wengao/Settings/TerminalB/Voltage"]
    assert callable(callback)
    assert callback("/Wengao/Settings/TerminalB/Voltage", 55.2) is True
    assert controller.calls == [("B-voltage", 55.2)]
    assert service.values["/State"] == 0


def test_auxiliary_battery_is_monitor_only_and_has_no_bms_limits() -> None:
    config = device_config(
        system_terminal="B",
        auxiliary_battery={
            "enabled": True,
            "terminal": "A",
            "device_instance": 80,
            "custom_name": "Auxiliary battery",
        },
    )
    service = FakeService()
    publisher = AuxiliaryBatteryPublisher(service, config, None)
    assert service.events[-1][0] == "register"
    assert service.values["/Connected"] == 0
    assert service.values["/Soc"] is None
    assert not any(path.startswith("/Info/") for path in service.values)
    assert not any(path.startswith("/Link/") for path in service.values)
    publisher.publish_identity(identity())
    publisher.publish(snapshot(mode=4))
    assert service.values["/Connected"] == 1
    assert service.values["/Dc/0/Voltage"] == 55.65
    assert service.values["/Dc/0/Current"] == -0.84
    assert service.values["/Dc/0/Power"] == -47


def test_auxiliary_battery_current_is_positive_when_energy_enters_terminal() -> None:
    config = device_config(
        system_terminal="A",
        auxiliary_battery={
            "enabled": True,
            "terminal": "B",
            "device_instance": 80,
            "custom_name": "Auxiliary battery",
        },
    )
    service = FakeService()
    publisher = AuxiliaryBatteryPublisher(service, config, identity())
    publisher.publish(snapshot(mode=4))
    assert service.values["/Dc/0/Voltage"] == 12.5
    assert service.values["/Dc/0/Current"] == 3.71
    assert service.values["/Dc/0/Power"] == 46
    publisher.mark_disconnected()
    assert service.values["/Connected"] == 0
    assert service.values["/Dc/0/Voltage"] is None
