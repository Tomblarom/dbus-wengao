from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from wengao.model import DeviceIdentity, RealtimeSnapshot, TerminalMeasurements
from wengao.venus.runner import run_service


class MemoryLastKnownVoltageStore:
    instances: ClassVar[list[MemoryLastKnownVoltageStore]] = []

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.voltage_v = 12.4
        self.observed_at = 1_700_000_000
        self.recorded: tuple[float, int] | None = None
        self.flushed = 0
        self.__class__.instances.append(self)

    def load(self) -> MemoryLastKnownVoltageStore:
        return self

    def record(self, voltage_v: float, *, observed_at: int) -> MemoryLastKnownVoltageStore:
        self.voltage_v = voltage_v
        self.observed_at = observed_at
        self.recorded = (voltage_v, observed_at)
        return self

    def flush_if_due(self) -> bool:
        self.flushed += 1
        return True

    def flush(self) -> bool:
        self.flushed += 1
        return True


class MemoryHistoryStore:
    instances: ClassVar[list[MemoryHistoryStore]] = []

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.operation_time = 0
        self.recorded = 0
        self.disconnected = 0
        self.__class__.instances.append(self)

    def load(self) -> bool:
        return False

    def record(self, _snapshot: RealtimeSnapshot) -> None:
        self.recorded += 1
        self.operation_time += 1

    def mark_disconnected(self) -> None:
        self.disconnected += 1

    def dbus_values(self) -> dict[str, object]:
        return {
            "/History/Cumulative/User/OperationTime": self.operation_time,
            "/History/Cycle/CyclesAvailable": 0,
        }

    def flush_if_due(self) -> bool:
        return False

    def flush(self) -> bool:
        return True


class FakeService:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.registered = False

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
        return object()

    def register(self) -> None:
        self.registered = True

    def __setitem__(self, path: str, value: object) -> None:
        self.values[path] = value


class FakeMainLoop:
    def run(self) -> None:
        return

    def quit(self) -> None:
        return


class FakeGlib:
    callback: Any = None

    @staticmethod
    def MainLoop() -> FakeMainLoop:  # noqa: N802 - mirrors GLib's public API
        return FakeMainLoop()

    @classmethod
    def timeout_add(cls, _milliseconds: int, callback: Any) -> int:
        cls.callback = callback
        return 1


class FakeHandle:
    def close(self) -> None:
        return


class FakePortLock:
    def acquire_for_port(self, _port: str) -> bool:
        return True

    def release(self) -> None:
        return


class FakeTransport:
    def __init__(self, _port: str, *, timeout: float) -> None:
        self.timeout = timeout
        self.closed = False

    def close(self) -> None:
        self.closed = True


def write_config(
    path: Path,
    *,
    unavailable_devices: str,
    auxiliary_battery: bool,
    display_last_known_voltage: bool = False,
) -> None:
    auxiliary = (
        f"""
[devices.auxiliary_battery]
enabled = true
terminal = "A"
device_instance = 80
custom_name = "Auxiliary battery"
display_last_known_voltage = {str(display_last_known_voltage).lower()}
"""
        if auxiliary_battery
        else ""
    )
    path.write_text(
        f"""config_version = 1
[[devices]]
id = "test-device"
enabled = true
profile = "vehicle-battery-link"
port = "/dev/serial/by-id/synthetic"
slave_address = 1
system_terminal = "B"
device_instance = 40
custom_name = "Test converter"
venus_role = "dcsystem"
control_mode = "monitor-only"
dvcc_policy = "disabled"
communication_timeout = 1.0
poll_interval = 2.0
allowed_directions = ["A-to-B", "B-to-A"]
locked_direction = ""
[devices.permissions]
{auxiliary}
[display]
unavailable_devices = "{unavailable_devices}"
""",
        encoding="utf-8",
    )


def snapshot() -> RealtimeSnapshot:
    return RealtimeSnapshot(
        terminal_a=TerminalMeasurements(12.6, 1.0, 13),
        terminal_b=TerminalMeasurements(54.0, 0.2, 11),
        temperature_t1_c=30,
        temperature_t2_c=31,
        power_mode=2,
        operating_mode=5,
        fault_bits=0,
        alarm_bits=0,
        acc_voltage_v=13.8,
        rmt_voltage_v=0.0,
        ambient_temperature_c=30,
        charging_state=2,
        raw_registers=(0,) * 16,
    )


def prepare_runtime(monkeypatch: pytest.MonkeyPatch) -> dict[str, FakeService]:
    services: dict[str, FakeService] = {}

    def service_class(name: str, *, register: bool) -> FakeService:
        assert register is False
        service = FakeService()
        services[name] = service
        return service

    runtime = SimpleNamespace(
        dbus_main_loop=lambda **_kwargs: None,
        glib=FakeGlib,
        service_class=service_class,
    )
    monkeypatch.setattr("wengao.venus.runner.load_venus_runtime", lambda: runtime)
    monkeypatch.setattr("wengao.venus.runner._lock_instance", lambda _device_id: FakeHandle())
    monkeypatch.setattr("wengao.venus.runner.SerialStarterPortLock", FakePortLock)
    monkeypatch.setattr("wengao.venus.runner.SerialRtuTransport", FakeTransport)
    MemoryHistoryStore.instances.clear()
    monkeypatch.setattr("wengao.venus.runner.ConverterHistoryStore", MemoryHistoryStore)
    monkeypatch.setattr("wengao.venus.runner.signal.signal", lambda *_args: None)
    return services


def test_zero_policy_publishes_offline_converter_and_auxiliary_battery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, unavailable_devices="zero", auxiliary_battery=True)
    services = prepare_runtime(monkeypatch)

    class OfflineProtocol:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return

        def test_connection(self) -> DeviceIdentity:
            raise OSError("offline")

    monkeypatch.setattr("wengao.venus.runner.WengaoProtocol", OfflineProtocol)
    assert run_service(config_path, "test-device") == 0
    assert set(services) == {
        "com.victronenergy.dcsystem.test_device",
        "com.victronenergy.battery.wengao_test_device_a",
    }
    assert services["com.victronenergy.dcsystem.test_device"].values["/Connected"] == 0
    assert services["com.victronenergy.dcsystem.test_device"].values["/WengaoShowUnavailable"] == 1
    auxiliary = services["com.victronenergy.battery.wengao_test_device_a"]
    assert auxiliary.values["/Connected"] == 0
    assert math.isnan(auxiliary.values["/Dc/0/Voltage"])


def test_hide_policy_does_not_publish_never_seen_converter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, unavailable_devices="hide", auxiliary_battery=False)
    services = prepare_runtime(monkeypatch)

    class OfflineProtocol:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return

        def test_connection(self) -> DeviceIdentity:
            raise OSError("offline")

    monkeypatch.setattr("wengao.venus.runner.WengaoProtocol", OfflineProtocol)
    assert run_service(config_path, "test-device") == 0
    assert services == {}


def test_successful_first_poll_publishes_both_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, unavailable_devices="hide", auxiliary_battery=True)
    services = prepare_runtime(monkeypatch)

    class OnlineProtocol:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return

        def test_connection(self) -> DeviceIdentity:
            return DeviceIdentity("V101", "V103", "V201", "SYNTHETIC", "WG-BC1500M", 1, 0)

        def read_realtime(self) -> RealtimeSnapshot:
            return snapshot()

    monkeypatch.setattr("wengao.venus.runner.WengaoProtocol", OnlineProtocol)
    assert run_service(config_path, "test-device") == 0
    converter = services["com.victronenergy.dcsystem.test_device"]
    auxiliary = services["com.victronenergy.battery.wengao_test_device_a"]
    assert converter.values["/Connected"] == 1
    assert converter.values["/Dc/0/Power"] == 11
    assert converter.values["/History/Cumulative/User/OperationTime"] == 1
    assert MemoryHistoryStore.instances[0].recorded == 1
    assert auxiliary.values["/Connected"] == 1
    assert auxiliary.values["/Dc/0/Voltage"] == 12.6
    assert auxiliary.values["/Dc/0/Power"] == 13


def test_runner_restores_and_persists_last_known_auxiliary_voltage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    write_config(
        config_path,
        unavailable_devices="zero",
        auxiliary_battery=True,
        display_last_known_voltage=True,
    )
    services = prepare_runtime(monkeypatch)
    MemoryLastKnownVoltageStore.instances.clear()
    monkeypatch.setattr(
        "wengao.venus.runner.LastKnownVoltageStore", MemoryLastKnownVoltageStore
    )

    class OnlineProtocol:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return

        def test_connection(self) -> DeviceIdentity:
            return DeviceIdentity("V101", "V103", "V201", "SYNTHETIC", "WG-BC1500M", 1, 0)

        def read_realtime(self) -> RealtimeSnapshot:
            return snapshot()

    monkeypatch.setattr("wengao.venus.runner.WengaoProtocol", OnlineProtocol)
    assert run_service(config_path, "test-device") == 0
    auxiliary = services["com.victronenergy.battery.wengao_test_device_a"]
    assert auxiliary.values["/Dc/0/Voltage"] == 12.6
    assert auxiliary.values["/Wengao/LastKnownVoltage"] == 12.6
    store = MemoryLastKnownVoltageStore.instances[0]
    assert store.recorded is not None
    assert store.recorded[0] == 12.6
    assert store.flushed >= 1
