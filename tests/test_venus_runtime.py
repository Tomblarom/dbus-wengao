from __future__ import annotations

from types import SimpleNamespace

from wengao.venus.runtime import _private_service_factory


def test_each_venus_service_uses_a_private_dbus_connection() -> None:
    buses: list[object] = []
    calls: list[tuple[str, object, bool]] = []

    class FakeDbus:
        @staticmethod
        def SystemBus(*, private: bool) -> object:  # noqa: N802 - mirrors dbus-python
            assert private is True
            bus = object()
            buses.append(bus)
            return bus

    class FakeService:
        def __init__(self, name: str, *, bus: object, register: bool) -> None:
            calls.append((name, bus, register))

    factory = _private_service_factory(
        SimpleNamespace(VeDbusService=FakeService),
        FakeDbus,
    )

    factory("com.victronenergy.dcsystem.first", register=False)
    factory("com.victronenergy.battery.second", register=False)

    assert len(buses) == 2
    assert buses[0] is not buses[1]
    assert calls == [
        ("com.victronenergy.dcsystem.first", buses[0], False),
        ("com.victronenergy.battery.second", buses[1], False),
    ]
