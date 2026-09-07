from __future__ import annotations

import json
import os
from pathlib import Path

from wengao.model import RealtimeSnapshot, TerminalMeasurements
from wengao.profiles import Direction, Terminal
from wengao.venus.history import ConverterHistoryStore


class Clock:
    def __init__(self) -> None:
        self.monotonic = 100.0
        self.wall = 1_700_000_000.0

    def advance(self, seconds: float) -> None:
        self.monotonic += seconds
        self.wall += seconds


def snapshot(
    *,
    direction: Direction = Direction.A_TO_B,
    charging_state: int = 2,
    power_w: int = 500,
    current_a: float = 10.0,
    fault_bits: int = 0,
) -> RealtimeSnapshot:
    return RealtimeSnapshot(
        terminal_a=TerminalMeasurements(52.0, current_a, power_w + 20),
        terminal_b=TerminalMeasurements(50.0, current_a, power_w),
        temperature_t1_c=35,
        temperature_t2_c=36,
        power_mode=2,
        operating_mode=4 if direction is Direction.A_TO_B else 5,
        fault_bits=fault_bits,
        alarm_bits=0,
        acc_voltage_v=12.0,
        rmt_voltage_v=0.0,
        ambient_temperature_c=34,
        charging_state=charging_state,
        raw_registers=(0,) * 16,
    )


def store(tmp_path: Path, clock: Clock, *, retention: int = 50) -> ConverterHistoryStore:
    return ConverterHistoryStore(
        tmp_path,
        "converter-1",
        Terminal.B,
        (Direction.A_TO_B, Direction.B_TO_A),
        poll_interval=2.0,
        cycle_retention=retention,
        flush_interval=10.0,
        wall_clock=lambda: clock.wall,
        monotonic_clock=lambda: clock.monotonic,
    )


def test_history_uses_orion_compatible_paths_and_integrates_successful_polls(
    tmp_path: Path,
) -> None:
    clock = Clock()
    history = store(tmp_path, clock)

    history.record(snapshot())
    clock.advance(2)
    history.record(snapshot())

    values = history.dbus_values()
    assert values["/History/Cumulative/User/OperationTime"] == 2
    assert values["/History/Cumulative/User/ChargedAh"] == 10 * 2 / 3600
    assert values["/History/Cumulative/User/EnergyAtoB"] == 500 * 2 / 3_600_000
    assert values["/History/Cumulative/User/EnergyToSystem"] == 500 * 2 / 3_600_000
    assert values["/History/Cumulative/User/EnergyFromSystem"] == 0
    assert values["/History/Cycle/0/BulkTime"] == 2
    assert values["/History/Cycle/0/BulkCharge"] == 10 * 2 / 3600
    assert values["/History/Cycle/0/WengaoDirection"] == "A-to-B"
    assert values["/History/Cycle/CyclesAvailable"] == 0
    assert values["/History/MinimumVoltage"] == 50.0
    assert values["/History/MaximumTemperature"] == 34.0


def test_natural_stop_completes_cycle_and_preserves_it_at_index_one(tmp_path: Path) -> None:
    clock = Clock()
    history = store(tmp_path, clock)
    history.record(snapshot())
    clock.advance(2)
    history.record(snapshot())
    clock.advance(2)
    history.record(snapshot(charging_state=5, power_w=0, current_a=0))

    values = history.dbus_values()
    assert values["/History/Cumulative/User/CyclesStarted"] == 1
    assert values["/History/Cumulative/User/CyclesCompleted"] == 1
    assert values["/History/Cycle/CyclesAvailable"] == 1
    assert values["/History/Cycle/0/StartTime"] is None
    assert values["/History/Cycle/1/TerminationReason"] == 1
    assert values["/History/Cycle/1/StartVoltage"] == 50.0
    assert values["/History/Cycle/1/EndVoltage"] == 50.0


def test_reverse_direction_is_counted_separately_and_as_energy_from_system(
    tmp_path: Path,
) -> None:
    clock = Clock()
    history = store(tmp_path, clock)
    history.record(snapshot(direction=Direction.B_TO_A))
    clock.advance(4)
    history.record(snapshot(direction=Direction.B_TO_A))

    values = history.dbus_values()
    assert values["/History/Cumulative/User/EnergyAtoB"] == 0
    assert values["/History/Cumulative/User/EnergyBtoA"] == 520 * 4 / 3_600_000
    assert values["/History/Cumulative/User/EnergyFromSystem"] == 520 * 4 / 3_600_000
    assert values["/History/Cumulative/User/OperationTimeBtoA"] == 4


def test_communication_gap_is_not_integrated_and_terminates_the_active_cycle(
    tmp_path: Path,
) -> None:
    clock = Clock()
    history = store(tmp_path, clock)
    history.record(snapshot())
    clock.advance(2)
    history.record(snapshot())
    history.mark_disconnected()
    clock.advance(60)
    history.record(snapshot())

    values = history.dbus_values()
    assert values["/History/Cumulative/User/OperationTime"] == 2
    assert values["/History/Cycle/CyclesAvailable"] == 1
    assert values["/History/Cycle/1/TerminationReason"] == 2
    assert values["/History/Cycle/0/WengaoDirection"] == "A-to-B"


def test_unreasonably_late_poll_is_not_integrated(tmp_path: Path) -> None:
    clock = Clock()
    history = store(tmp_path, clock)
    history.record(snapshot())
    clock.advance(10)
    history.record(snapshot())
    assert history.dbus_values()["/History/Cumulative/User/OperationTime"] == 0


def test_history_persists_active_and_completed_cycles_atomically(tmp_path: Path) -> None:
    clock = Clock()
    original = store(tmp_path, clock, retention=2)
    original.record(snapshot())
    clock.advance(2)
    original.record(snapshot())
    original.record(snapshot(charging_state=5, power_w=0, current_a=0))
    assert original.flush()
    if os.name != "nt":
        assert original.path.stat().st_mode & 0o777 == 0o600

    restored = store(tmp_path, clock, retention=2)
    assert restored.load()
    values = restored.dbus_values()
    assert values["/History/Cumulative/User/OperationTime"] == 2
    assert values["/History/Cycle/CyclesAvailable"] == 1
    assert values["/History/Cycle/1/TerminationReason"] == 1


def test_unchanged_idle_measurements_do_not_cause_periodic_disk_writes(
    tmp_path: Path,
) -> None:
    clock = Clock()
    history = store(tmp_path, clock)
    idle = snapshot(charging_state=5, power_w=0, current_a=0)

    history.record(idle)
    assert history.flush()
    clock.advance(20)
    history.record(idle)

    assert not history.flush_if_due()


def test_invalid_or_mismatched_history_is_ignored(tmp_path: Path) -> None:
    clock = Clock()
    history = store(tmp_path, clock)
    history.path.write_text(
        json.dumps(
            {
                "version": 1,
                "device_id": "another-device",
                "system_terminal": "B",
                "cumulative": {},
            }
        ),
        encoding="utf-8",
    )
    assert not history.load()
    assert history.dbus_values()["/History/Cumulative/User/OperationTime"] == 0


def test_retention_keeps_only_the_newest_completed_cycles(tmp_path: Path) -> None:
    clock = Clock()
    history = store(tmp_path, clock, retention=2)
    for _index in range(3):
        history.record(snapshot())
        clock.advance(2)
        history.record(snapshot())
        history.record(snapshot(charging_state=5, power_w=0, current_a=0))
        clock.advance(1)

    values = history.dbus_values()
    assert values["/History/Cumulative/User/CyclesStarted"] == 3
    assert values["/History/Cycle/CyclesAvailable"] == 2
    assert "/History/Cycle/2/TerminationReason" in values
    assert "/History/Cycle/3/TerminationReason" not in values
