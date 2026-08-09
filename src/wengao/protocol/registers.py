"""Register evidence plus conservative decoding of supported values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from wengao.errors import UnexpectedResponseError
from wengao.model import DeviceIdentity, RealtimeSnapshot, TerminalMeasurements, TerminalSetpoints


class Confidence(StrEnum):
    DOCUMENTED_BC900M = "documented-bc900m"
    DOCUMENTED_WG48BC1500M = "documented-wg48bc1500m"
    APP_SOURCE_CONFIRMED = "app-source-confirmed"
    OBSERVED_RS485 = "observed-rs485"
    EXPERIMENTALLY_CONFIRMED = "experimentally-confirmed"
    CONTRADICTORY = "contradictory"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RegisterDefinition:
    address: int
    name: str
    scale: float
    unit: str | None
    confidence: tuple[Confidence, ...]
    writable: bool = False


REALTIME_START = 0x0200
REALTIME_COUNT = 16
IDENTITY_START = 0x0000
IDENTITY_COUNT = 30
REMOTE_OUTPUT_REGISTER = 0x0401
TERMINAL_A_SETTINGS_START = 0x081A
TERMINAL_B_SETTINGS_START = 0x081D
TERMINAL_SETTINGS_COUNT = 3

CONTROL_REGISTERS: tuple[RegisterDefinition, ...] = (
    RegisterDefinition(
        REMOTE_OUTPUT_REGISTER,
        "remote_shutdown",
        1,
        None,
        (Confidence.DOCUMENTED_BC900M, Confidence.APP_SOURCE_CONFIRMED),
        writable=True,
    ),
    RegisterDefinition(
        TERMINAL_A_SETTINGS_START,
        "terminal_a_voltage_setpoint",
        0.01,
        "V",
        (Confidence.DOCUMENTED_BC900M, Confidence.APP_SOURCE_CONFIRMED),
        writable=True,
    ),
    RegisterDefinition(
        TERMINAL_A_SETTINGS_START + 1,
        "terminal_a_current_setpoint",
        0.01,
        "A",
        (Confidence.DOCUMENTED_BC900M, Confidence.APP_SOURCE_CONFIRMED),
        writable=True,
    ),
    RegisterDefinition(
        TERMINAL_A_SETTINGS_START + 2,
        "terminal_a_power_setpoint",
        1,
        "W",
        (Confidence.DOCUMENTED_BC900M, Confidence.APP_SOURCE_CONFIRMED),
        writable=True,
    ),
    RegisterDefinition(
        TERMINAL_B_SETTINGS_START,
        "terminal_b_voltage_setpoint",
        0.01,
        "V",
        (Confidence.DOCUMENTED_BC900M, Confidence.APP_SOURCE_CONFIRMED),
        writable=True,
    ),
    RegisterDefinition(
        TERMINAL_B_SETTINGS_START + 1,
        "terminal_b_current_setpoint",
        0.01,
        "A",
        (Confidence.DOCUMENTED_BC900M, Confidence.APP_SOURCE_CONFIRMED),
        writable=True,
    ),
    RegisterDefinition(
        TERMINAL_B_SETTINGS_START + 2,
        "terminal_b_power_setpoint",
        1,
        "W",
        (Confidence.DOCUMENTED_BC900M, Confidence.APP_SOURCE_CONFIRMED),
        writable=True,
    ),
)

REALTIME_REGISTERS: tuple[RegisterDefinition, ...] = (
    RegisterDefinition(0x0200, "terminal_a_voltage", 0.01, "V", (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(0x0201, "terminal_a_current", 0.01, "A", (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(0x0202, "terminal_a_power", 1, "W", (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(0x0203, "terminal_b_voltage", 0.01, "V", (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(0x0204, "terminal_b_current", 0.01, "A", (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(0x0205, "terminal_b_power", 1, "W", (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(0x0206, "temperature_t1", 1, "degC", (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(0x0207, "temperature_t2", 1, "degC", (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(0x0208, "power_mode", 1, None, (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(0x0209, "operating_mode", 1, None, (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(0x020A, "fault_bits", 1, None, (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(0x020B, "alarm_bits", 1, None, (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(
        0x020C,
        "acc_voltage",
        0.01,
        "V",
        (Confidence.OBSERVED_RS485, Confidence.CONTRADICTORY),
    ),
    RegisterDefinition(
        0x020D,
        "rmt_voltage",
        0.01,
        "V",
        (Confidence.OBSERVED_RS485, Confidence.CONTRADICTORY),
    ),
    RegisterDefinition(0x020E, "ambient_temperature", 1, "degC", (Confidence.OBSERVED_RS485,)),
    RegisterDefinition(
        0x020F,
        "charging_state",
        1,
        None,
        (Confidence.OBSERVED_RS485, Confidence.CONTRADICTORY),
    ),
)


def decode_realtime(registers: tuple[int, ...]) -> RealtimeSnapshot:
    if len(registers) != REALTIME_COUNT:
        raise UnexpectedResponseError(
            f"real-time block contains {len(registers)} registers; expected {REALTIME_COUNT}"
        )
    return RealtimeSnapshot(
        terminal_a=TerminalMeasurements(registers[0] / 100, registers[1] / 100, registers[2]),
        terminal_b=TerminalMeasurements(registers[3] / 100, registers[4] / 100, registers[5]),
        temperature_t1_c=registers[6],
        temperature_t2_c=registers[7],
        power_mode=registers[8],
        operating_mode=registers[9],
        fault_bits=registers[10],
        alarm_bits=registers[11],
        acc_voltage_v=registers[12] / 100,
        rmt_voltage_v=registers[13] / 100,
        ambient_temperature_c=registers[14],
        charging_state=registers[15],
        raw_registers=registers,
    )


def decode_identity(registers: tuple[int, ...]) -> DeviceIdentity:
    if len(registers) != IDENTITY_COUNT:
        raise UnexpectedResponseError(
            f"identity block contains {len(registers)} registers; expected {IDENTITY_COUNT}"
        )
    payload = b"".join(value.to_bytes(2, "big") for value in registers)

    def text(start_register: int, register_count: int) -> str:
        start = start_register * 2
        end = start + register_count * 2
        return payload[start:end].decode("ascii", "replace").rstrip(" \x00")

    return DeviceIdentity(
        protocol_version=text(0, 2),
        hardware_version=text(4, 2),
        firmware_version=text(6, 2),
        serial_number=text(8, 10),
        model=text(18, 10),
        configured_address=registers[28],
        scenario=registers[29],
    )


def decode_terminal_setpoints(registers: tuple[int, ...]) -> TerminalSetpoints:
    if len(registers) != TERMINAL_SETTINGS_COUNT:
        raise UnexpectedResponseError(
            f"setpoint block contains {len(registers)} registers; "
            f"expected {TERMINAL_SETTINGS_COUNT}"
        )
    return TerminalSetpoints(registers[0] / 100, registers[1] / 100, registers[2])


def encode_terminal_setpoints(settings: TerminalSetpoints) -> tuple[int, int, int]:
    voltage = round(settings.voltage_v * 100)
    current = round(settings.current_a * 100)
    power = settings.power_w
    values = (voltage, current, power)
    if any(not isinstance(value, int) or not 0 <= value <= 0xFFFF for value in values):
        raise ValueError("setpoint values must fit their unsigned 16-bit registers")
    return values
