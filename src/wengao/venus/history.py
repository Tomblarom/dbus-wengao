"""Persistent converter statistics using Victron's DC-charger history paths."""

from __future__ import annotations

import json
import logging
import math
import os
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from wengao.model import RealtimeSnapshot, TerminalMeasurements
from wengao.profiles import Direction, Terminal, direction_from_operating_mode

STATE_VERSION = 1
DEFAULT_CYCLE_RETENTION = 50
DEFAULT_FLUSH_INTERVAL = 300.0
DEFAULT_ACTIVE_POWER_THRESHOLD_W = 1.0

_PHASES = ("bulk", "absorption", "recondition", "float", "storage")
_PHASE_DBUS_NAMES = {
    "bulk": "Bulk",
    "absorption": "Absorption",
    "recondition": "Recondition",
    "float": "Float",
    "storage": "Storage",
}
_CYCLE_FIELDS = (
    "BatteryType",
    "StartTime",
    "StartVoltage",
    "EndVoltage",
    "TerminationReason",
    "Error",
    "BulkTime",
    "AbsorptionTime",
    "ReconditionTime",
    "FloatTime",
    "StorageTime",
    "BulkCharge",
    "AbsorptionCharge",
    "ReconditionCharge",
    "FloatCharge",
    "StorageCharge",
    "WengaoDirection",
    "WengaoEnergy",
)


@dataclass(slots=True)
class ConverterCycle:
    direction: Direction
    start_time: int
    start_voltage_v: float
    end_voltage_v: float | None = None
    termination_reason: int | None = None
    error: int = 0
    phase_time_s: dict[str, float] = field(
        default_factory=lambda: dict.fromkeys(_PHASES, 0.0)
    )
    phase_charge_ah: dict[str, float] = field(
        default_factory=lambda: dict.fromkeys(_PHASES, 0.0)
    )
    energy_kwh: float = 0.0

    def as_mapping(self) -> dict[str, object]:
        return {
            "direction": self.direction.value,
            "start_time": self.start_time,
            "start_voltage_v": self.start_voltage_v,
            "end_voltage_v": self.end_voltage_v,
            "termination_reason": self.termination_reason,
            "error": self.error,
            "phase_time_s": self.phase_time_s,
            "phase_charge_ah": self.phase_charge_ah,
            "energy_kwh": self.energy_kwh,
        }

    @classmethod
    def from_mapping(cls, raw: object) -> ConverterCycle:
        if not isinstance(raw, dict):
            raise ValueError("cycle must be an object")
        phase_time = _phase_values(raw.get("phase_time_s"))
        phase_charge = _phase_values(raw.get("phase_charge_ah"))
        end_voltage = _optional_finite(raw.get("end_voltage_v"))
        termination = raw.get("termination_reason")
        if termination is not None and (
            isinstance(termination, bool) or not isinstance(termination, int)
        ):
            raise ValueError("cycle termination reason must be an integer or null")
        cycle = cls(
            direction=Direction(str(raw["direction"])),
            start_time=_positive_integer(raw.get("start_time"), "cycle start time"),
            start_voltage_v=_non_negative_finite(
                raw.get("start_voltage_v"), "cycle start voltage"
            ),
            end_voltage_v=end_voltage,
            termination_reason=termination,
            error=_non_negative_integer(raw.get("error", 0), "cycle error"),
            phase_time_s=phase_time,
            phase_charge_ah=phase_charge,
            energy_kwh=_non_negative_finite(raw.get("energy_kwh", 0), "cycle energy"),
        )
        return cycle


@dataclass(slots=True)
class CumulativeHistory:
    operation_time_s: float = 0.0
    charged_ah: float = 0.0
    cycles_started: int = 0
    cycles_completed: int = 0
    energy_to_system_kwh: float = 0.0
    energy_from_system_kwh: float = 0.0
    energy_a_to_b_kwh: float = 0.0
    energy_b_to_a_kwh: float = 0.0
    charged_ah_a_to_b: float = 0.0
    charged_ah_b_to_a: float = 0.0
    operation_time_a_to_b_s: float = 0.0
    operation_time_b_to_a_s: float = 0.0
    minimum_voltage_v: float | None = None
    maximum_voltage_v: float | None = None
    minimum_temperature_c: float | None = None
    maximum_temperature_c: float | None = None

    def as_mapping(self) -> dict[str, object]:
        return {
            key: getattr(self, key)
            for key in self.__dataclass_fields__
        }

    @classmethod
    def from_mapping(cls, raw: object) -> CumulativeHistory:
        if not isinstance(raw, dict):
            raise ValueError("cumulative history must be an object")
        result = cls()
        integer_fields = {"cycles_started", "cycles_completed"}
        optional_fields = {
            "minimum_voltage_v",
            "maximum_voltage_v",
            "minimum_temperature_c",
            "maximum_temperature_c",
        }
        for name in result.__dataclass_fields__:
            value = raw.get(name, getattr(result, name))
            if name in integer_fields:
                setattr(result, name, _non_negative_integer(value, name))
            elif name in optional_fields:
                setattr(result, name, _optional_finite(value))
            else:
                setattr(result, name, _non_negative_finite(value, name))
        return result


class ConverterHistoryStore:
    """Accumulate history without writing to the Wengao device.

    Energy and charge are integrated only between consecutive successful polls. Communication
    gaps are never counted. Completed cycles are newest-first and cycle zero is reserved for the
    active cycle, matching the path layout used by Victron Orion XS devices.
    """

    def __init__(
        self,
        state_directory: Path,
        device_id: str,
        system_terminal: Terminal,
        allowed_directions: tuple[Direction, ...],
        *,
        poll_interval: float,
        cycle_retention: int = DEFAULT_CYCLE_RETENTION,
        active_power_threshold_w: float = DEFAULT_ACTIVE_POWER_THRESHOLD_W,
        flush_interval: float = DEFAULT_FLUSH_INTERVAL,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if cycle_retention < 1:
            raise ValueError("cycle retention must be positive")
        if active_power_threshold_w < 0:
            raise ValueError("active power threshold must not be negative")
        self._path = state_directory / f"{device_id}-history.json"
        self._device_id = device_id
        self._system_terminal = system_terminal
        self._allowed_directions = frozenset(allowed_directions)
        self._poll_interval = poll_interval
        self._cycle_retention = cycle_retention
        self._active_power_threshold_w = active_power_threshold_w
        self._flush_interval = flush_interval
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._cumulative = CumulativeHistory()
        self._active_cycle: ConverterCycle | None = None
        self._completed_cycles: list[ConverterCycle] = []
        self._last_sample_at: float | None = None
        self._last_flush_at: float | None = None
        self._dirty = False

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> bool:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("version") != STATE_VERSION:
                raise ValueError("unsupported history state format")
            if raw.get("device_id") != self._device_id:
                raise ValueError("history belongs to another device")
            if raw.get("system_terminal") != self._system_terminal.value:
                raise ValueError("configured system terminal changed")
            cumulative = CumulativeHistory.from_mapping(raw.get("cumulative"))
            active_raw = raw.get("active_cycle")
            active = None if active_raw is None else ConverterCycle.from_mapping(active_raw)
            completed_raw = raw.get("completed_cycles", [])
            if not isinstance(completed_raw, list):
                raise ValueError("completed cycles must be an array")
            completed = [ConverterCycle.from_mapping(item) for item in completed_raw]
            if active is not None and active.termination_reason is not None:
                raise ValueError("active cycle is already terminated")
            if any(cycle.termination_reason is None for cycle in completed):
                raise ValueError("completed cycle has no termination reason")
        except FileNotFoundError:
            return False
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            logging.warning("ignoring invalid converter history %s: %s", self._path, error)
            return False
        self._cumulative = cumulative
        self._active_cycle = active
        self._completed_cycles = completed[: self._cycle_retention]
        self._last_sample_at = None
        self._last_flush_at = self._monotonic_clock()
        self._dirty = False
        return True

    def record(self, snapshot: RealtimeSnapshot) -> None:
        now = self._monotonic_clock()
        observed_at = int(self._wall_clock())
        direction = direction_from_operating_mode(snapshot.operating_mode)
        allowed = direction is not None and direction in self._allowed_directions
        self._record_bounds(snapshot)
        if not allowed or direction is None:
            self._close_active(snapshot, termination_reason=4)
            self._last_sample_at = None
            return

        source, destination = _flow_measurements(snapshot, direction)
        active = (
            snapshot.charging_state != 5
            and max(source.power_w, destination.power_w) > self._active_power_threshold_w
        )
        if not active:
            reason = 0 if snapshot.fault_bits or snapshot.alarm_bits else 1
            self._close_active(snapshot, termination_reason=reason)
            self._last_sample_at = None
            return

        if self._active_cycle is None:
            self._start_cycle(direction, destination, observed_at)
            self._last_sample_at = now
            return
        if self._active_cycle.direction is not direction:
            self._close_active(snapshot, termination_reason=4)
            self._start_cycle(direction, destination, observed_at)
            self._last_sample_at = now
            return

        elapsed = 0.0 if self._last_sample_at is None else now - self._last_sample_at
        self._last_sample_at = now
        maximum_gap = max(5.0, self._poll_interval * 2.5)
        if not 0 < elapsed <= maximum_gap:
            return
        self._accumulate(snapshot, direction, destination, elapsed)

    def mark_disconnected(self) -> None:
        self._close_active(None, termination_reason=2)
        self._last_sample_at = None

    def flush_if_due(self) -> bool:
        if not self._dirty:
            return False
        if (
            self._last_flush_at is not None
            and self._monotonic_clock() - self._last_flush_at < self._flush_interval
        ):
            return False
        return self.flush()

    def flush(self) -> bool:
        if not self._dirty:
            return False
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = {
            "version": STATE_VERSION,
            "device_id": self._device_id,
            "system_terminal": self._system_terminal.value,
            "cumulative": self._cumulative.as_mapping(),
            "active_cycle": self._active_cycle.as_mapping() if self._active_cycle else None,
            "completed_cycles": [cycle.as_mapping() for cycle in self._completed_cycles],
        }
        try:
            self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            temporary.chmod(0o600)
            os.replace(temporary, self._path)
        except OSError as error:
            logging.warning("cannot persist converter history %s: %s", self._path, error)
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            return False
        self._dirty = False
        self._last_flush_at = self._monotonic_clock()
        return True

    def dbus_values(self) -> Mapping[str, object]:
        cumulative = self._cumulative
        values: dict[str, object] = {
            "/History/Cumulative/User/OperationTime": round(cumulative.operation_time_s),
            "/History/Cumulative/User/ChargedAh": cumulative.charged_ah,
            "/History/Cumulative/User/CyclesStarted": cumulative.cycles_started,
            "/History/Cumulative/User/CyclesCompleted": cumulative.cycles_completed,
            "/History/Cumulative/User/EnergyToSystem": cumulative.energy_to_system_kwh,
            "/History/Cumulative/User/EnergyFromSystem": cumulative.energy_from_system_kwh,
            "/History/Cumulative/User/EnergyAtoB": cumulative.energy_a_to_b_kwh,
            "/History/Cumulative/User/EnergyBtoA": cumulative.energy_b_to_a_kwh,
            "/History/Cumulative/User/ChargedAhAtoB": cumulative.charged_ah_a_to_b,
            "/History/Cumulative/User/ChargedAhBtoA": cumulative.charged_ah_b_to_a,
            "/History/Cumulative/User/OperationTimeAtoB": round(
                cumulative.operation_time_a_to_b_s
            ),
            "/History/Cumulative/User/OperationTimeBtoA": round(
                cumulative.operation_time_b_to_a_s
            ),
            "/History/MinimumVoltage": cumulative.minimum_voltage_v,
            "/History/MaximumVoltage": cumulative.maximum_voltage_v,
            "/History/MinimumTemperature": cumulative.minimum_temperature_c,
            "/History/MaximumTemperature": cumulative.maximum_temperature_c,
            "/History/EnergyOut": cumulative.energy_to_system_kwh,
            "/History/EnergyIn": cumulative.energy_from_system_kwh,
            "/History/Cycle/CyclesAvailable": len(self._completed_cycles),
        }
        for index in range(self._cycle_retention + 1):
            cycle = (
                self._active_cycle
                if index == 0
                else (
                    self._completed_cycles[index - 1]
                    if index <= len(self._completed_cycles)
                    else None
                )
            )
            values.update(_cycle_dbus_values(index, cycle))
        return values

    def _record_bounds(self, snapshot: RealtimeSnapshot) -> None:
        system = (
            snapshot.terminal_a
            if self._system_terminal is Terminal.A
            else snapshot.terminal_b
        )
        cumulative = self._cumulative
        updated = (
            _minimum(cumulative.minimum_voltage_v, system.voltage_v),
            _maximum(cumulative.maximum_voltage_v, system.voltage_v),
            _minimum(
                cumulative.minimum_temperature_c,
                float(snapshot.ambient_temperature_c),
            ),
            _maximum(
                cumulative.maximum_temperature_c,
                float(snapshot.ambient_temperature_c),
            ),
        )
        previous = (
            cumulative.minimum_voltage_v,
            cumulative.maximum_voltage_v,
            cumulative.minimum_temperature_c,
            cumulative.maximum_temperature_c,
        )
        (
            cumulative.minimum_voltage_v,
            cumulative.maximum_voltage_v,
            cumulative.minimum_temperature_c,
            cumulative.maximum_temperature_c,
        ) = updated
        if updated != previous:
            self._dirty = True

    def _start_cycle(
        self, direction: Direction, destination: TerminalMeasurements, observed_at: int
    ) -> None:
        self._active_cycle = ConverterCycle(direction, observed_at, destination.voltage_v)
        self._cumulative.cycles_started += 1
        self._dirty = True

    def _close_active(
        self, snapshot: RealtimeSnapshot | None, *, termination_reason: int
    ) -> None:
        cycle = self._active_cycle
        if cycle is None:
            return
        if snapshot is not None:
            _, destination = _flow_measurements(snapshot, cycle.direction)
            cycle.end_voltage_v = destination.voltage_v
        cycle.termination_reason = termination_reason
        if termination_reason == 1:
            self._cumulative.cycles_completed += 1
        self._completed_cycles.insert(0, cycle)
        del self._completed_cycles[self._cycle_retention :]
        self._active_cycle = None
        self._dirty = True

    def _accumulate(
        self,
        snapshot: RealtimeSnapshot,
        direction: Direction,
        destination: TerminalMeasurements,
        elapsed_s: float,
    ) -> None:
        cycle = self._active_cycle
        if cycle is None:
            return
        phase = _phase_for_charging_state(snapshot.charging_state)
        charge_ah = destination.current_a * elapsed_s / 3600.0
        energy_kwh = destination.power_w * elapsed_s / 3_600_000.0
        cycle.phase_time_s[phase] += elapsed_s
        cycle.phase_charge_ah[phase] += charge_ah
        cycle.energy_kwh += energy_kwh

        cumulative = self._cumulative
        cumulative.operation_time_s += elapsed_s
        cumulative.charged_ah += charge_ah
        source_terminal = Terminal.A if direction is Direction.A_TO_B else Terminal.B
        destination_terminal = Terminal.B if direction is Direction.A_TO_B else Terminal.A
        if destination_terminal is self._system_terminal:
            cumulative.energy_to_system_kwh += energy_kwh
        elif source_terminal is self._system_terminal:
            cumulative.energy_from_system_kwh += energy_kwh
        if direction is Direction.A_TO_B:
            cumulative.energy_a_to_b_kwh += energy_kwh
            cumulative.charged_ah_a_to_b += charge_ah
            cumulative.operation_time_a_to_b_s += elapsed_s
        else:
            cumulative.energy_b_to_a_kwh += energy_kwh
            cumulative.charged_ah_b_to_a += charge_ah
            cumulative.operation_time_b_to_a_s += elapsed_s
        self._dirty = True


def _flow_measurements(
    snapshot: RealtimeSnapshot, direction: Direction
) -> tuple[TerminalMeasurements, TerminalMeasurements]:
    if direction is Direction.A_TO_B:
        return snapshot.terminal_a, snapshot.terminal_b
    return snapshot.terminal_b, snapshot.terminal_a


def _phase_for_charging_state(charging_state: int) -> str:
    # Wengao: 0 power supply, 1 pre-charge, 2 CC, 3 CV, 4 float, 5 stopped.
    # Unknown active states remain accounted as storage/other time instead of being discarded.
    return {1: "bulk", 2: "bulk", 3: "absorption", 4: "float"}.get(
        charging_state, "storage"
    )


def _cycle_dbus_values(index: int, cycle: ConverterCycle | None) -> dict[str, object]:
    prefix = f"/History/Cycle/{index}"
    if cycle is None:
        return {f"{prefix}/{field}": None for field in _CYCLE_FIELDS}
    values: dict[str, object] = {
        f"{prefix}/BatteryType": None,
        f"{prefix}/StartTime": cycle.start_time,
        f"{prefix}/StartVoltage": cycle.start_voltage_v,
        f"{prefix}/EndVoltage": cycle.end_voltage_v,
        f"{prefix}/TerminationReason": cycle.termination_reason,
        f"{prefix}/Error": cycle.error,
        f"{prefix}/WengaoDirection": cycle.direction.value,
        f"{prefix}/WengaoEnergy": cycle.energy_kwh,
    }
    for phase in _PHASES:
        dbus_name = _PHASE_DBUS_NAMES[phase]
        values[f"{prefix}/{dbus_name}Time"] = round(cycle.phase_time_s[phase])
        values[f"{prefix}/{dbus_name}Charge"] = cycle.phase_charge_ah[phase]
    return values


def _phase_values(raw: object) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise ValueError("phase values must be an object")
    return {
        phase: _non_negative_finite(raw.get(phase, 0), f"phase {phase}")
        for phase in _PHASES
    }


def _positive_integer(value: object, name: str) -> int:
    result = _non_negative_integer(value, name)
    if result == 0:
        raise ValueError(f"{name} must be positive")
    return result


def _non_negative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _non_negative_finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _optional_finite(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("optional value must be numeric or null")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("optional value must be finite")
    return result


def _minimum(current: float | None, value: float) -> float:
    return value if current is None else min(current, value)


def _maximum(current: float | None, value: float) -> float:
    return value if current is None else max(current, value)
