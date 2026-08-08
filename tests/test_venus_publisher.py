from __future__ import annotations

from typing import Any

from wengao.config import DeviceConfig, parse_config
from wengao.model import DeviceIdentity, RealtimeSnapshot, TerminalMeasurements
from wengao.venus.publisher import VenusPublisher, service_name


class FakeService:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.events: list[tuple[str, str, object]] = []
        self.set_count = 0

    def add_path(
        self,
        path: str,
        value: object,
        description: str = "",
        writeable: bool = False,
        **kwargs: object,
    ) -> object:
        assert writeable is False
        self.values[path] = value
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
                "port": "/dev/serial/by-path/synthetic",
                "slave_address": 1,
                "system_terminal": system_terminal,
                "device_instance": 40,
                "custom_name": "Wengao DC-DC",
                "venus_role": role,
                "control_mode": "monitor-only",
                "dvcc_policy": "disabled",
                "allowed_directions": directions,
                "locked_direction": locked,
                "permissions": {},
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
    assert not any(path.startswith("/Link/") for path in service.values)


def test_service_name_uses_role_and_dbus_safe_device_id() -> None:
    assert service_name(device_config(device_id="rear-converter")) == (
        "com.victronenergy.dcsystem.rear_converter"
    )


def test_dc_system_sign_is_positive_when_power_leaves_system_terminal() -> None:
    service, publisher = create_publisher(device_config(system_terminal="A"))
    publisher.publish(snapshot(mode=4))
    assert service.values["/Dc/0/Voltage"] == 55.65
    assert service.values["/Dc/0/Current"] == 0.84
    assert service.values["/Dc/0/Power"] == 47


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
    assert service.values["/Settings/BmsPresent"] == 0
    assert not any(path.startswith("/Link/") for path in service.values)


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


def test_disconnect_invalidates_measurements_and_marks_alarm() -> None:
    service, publisher = create_publisher(device_config())
    publisher.publish(snapshot())
    publisher.mark_disconnected()
    assert service.values["/Connected"] == 0
    assert service.values["/Alarms/Communication"] == 2
    assert service.values["/Dc/0/Voltage"] is None
    assert service.values["/Wengao/TerminalA/Voltage"] is None
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
    assert service.values["/State"] == 0
