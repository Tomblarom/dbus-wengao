"""Venus-independent device data model."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    protocol_version: str
    hardware_version: str
    firmware_version: str
    serial_number: str
    model: str
    configured_address: int
    scenario: int

    def safe_mapping(self) -> dict[str, Any]:
        """Return identity data suitable for logs and public diagnostics.

        Serial numbers are deliberately omitted. The digest is useful locally for comparing
        devices without exposing the original identifier, but is opt-in.
        """

        return {
            "protocol_version": self.protocol_version,
            "hardware_version": self.hardware_version,
            "firmware_version": self.firmware_version,
            "model": self.model,
            "configured_address": self.configured_address,
            "scenario": self.scenario,
        }

    def serial_digest(self) -> str:
        return sha256(self.serial_number.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TerminalMeasurements:
    voltage_v: float
    current_a: float
    power_w: int


@dataclass(frozen=True, slots=True)
class TerminalSetpoints:
    voltage_v: float
    current_a: float
    power_w: int


@dataclass(frozen=True, slots=True)
class ControlSettings:
    remote_enabled: bool
    terminal_a: TerminalSetpoints
    terminal_b: TerminalSetpoints


@dataclass(frozen=True, slots=True)
class RealtimeSnapshot:
    terminal_a: TerminalMeasurements
    terminal_b: TerminalMeasurements
    temperature_t1_c: int
    temperature_t2_c: int
    power_mode: int
    operating_mode: int
    fault_bits: int
    alarm_bits: int
    acc_voltage_v: float
    rmt_voltage_v: float
    ambient_temperature_c: int
    charging_state: int
    raw_registers: tuple[int, ...]

    def safe_mapping(self) -> dict[str, Any]:
        return {
            "terminal_a": {
                "voltage_v": self.terminal_a.voltage_v,
                "current_a": self.terminal_a.current_a,
                "power_w": self.terminal_a.power_w,
            },
            "terminal_b": {
                "voltage_v": self.terminal_b.voltage_v,
                "current_a": self.terminal_b.current_a,
                "power_w": self.terminal_b.power_w,
            },
            "temperature_t1_c": self.temperature_t1_c,
            "temperature_t2_c": self.temperature_t2_c,
            "power_mode": self.power_mode,
            "operating_mode": self.operating_mode,
            "fault_bits": self.fault_bits,
            "alarm_bits": self.alarm_bits,
            "acc_voltage_v": self.acc_voltage_v,
            "rmt_voltage_v": self.rmt_voltage_v,
            "ambient_temperature_c": self.ambient_temperature_c,
            "charging_state": self.charging_state,
        }

    def plausibility_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        for name, terminal in (("A", self.terminal_a), ("B", self.terminal_b)):
            if not 0 <= terminal.voltage_v <= 65:
                errors.append(f"terminal {name} voltage outside 0..65 V")
            if not 0 <= terminal.current_a <= 120:
                errors.append(f"terminal {name} current outside 0..120 A")
            if not 0 <= terminal.power_w <= 2000:
                errors.append(f"terminal {name} power outside 0..2000 W")
        for name, value in (
            ("T1", self.temperature_t1_c),
            ("T2", self.temperature_t2_c),
            ("Ta", self.ambient_temperature_c),
        ):
            if not 0 <= value <= 150:
                errors.append(f"temperature {name} outside the verified unsigned range")
        if not 0 <= self.acc_voltage_v <= 65:
            errors.append("ACC voltage outside 0..65 V")
        if not 0 <= self.rmt_voltage_v <= 65:
            errors.append("RMT voltage outside 0..65 V")
        return tuple(errors)
