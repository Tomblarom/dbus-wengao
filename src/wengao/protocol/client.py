"""Wengao protocol client with narrowly scoped, explicitly invoked writes."""

from __future__ import annotations

import time
from typing import Protocol

from wengao.errors import ResponseTimeoutError, UnsupportedDeviceError
from wengao.model import ControlSettings, DeviceIdentity, RealtimeSnapshot, TerminalSetpoints

from .capture import CaptureWriter
from .frame import (
    ReadHoldingRequest,
    WriteMultipleRegistersRequest,
    WriteSingleRegisterRequest,
    parse_read_holding_response,
    parse_write_multiple_response,
    parse_write_single_response,
)
from .registers import (
    IDENTITY_COUNT,
    IDENTITY_START,
    REALTIME_COUNT,
    REALTIME_START,
    REMOTE_OUTPUT_REGISTER,
    TERMINAL_A_SETTINGS_START,
    TERMINAL_B_SETTINGS_START,
    TERMINAL_SETTINGS_COUNT,
    decode_identity,
    decode_realtime,
    decode_terminal_setpoints,
)


class Transport(Protocol):
    def exchange(self, request: bytes) -> bytes: ...


SUPPORTED_INTERNAL_MODELS = frozenset({"WG-BC1500M", "WG-48BC1500M"})


class WengaoProtocol:
    """Protocol operations; policy and permissions belong to the control layer."""

    def __init__(
        self,
        transport: Transport,
        *,
        slave_address: int = 1,
        capture: CaptureWriter | None = None,
    ) -> None:
        self._transport = transport
        self._slave_address = slave_address
        self._capture = capture

    def read_holding_registers(
        self, start_register: int, register_count: int, *, sensitive_response: bool = False
    ) -> tuple[int, ...]:
        request = ReadHoldingRequest(self._slave_address, start_register, register_count).to_frame()
        response = b""
        started = time.monotonic()
        try:
            response = self._transport.exchange(request)
            registers = parse_read_holding_response(
                response,
                expected_address=self._slave_address,
                expected_register_count=register_count,
            )
        except Exception as error:
            if isinstance(error, ResponseTimeoutError):
                response = error.partial_response
            self._record(
                request,
                response,
                start_register,
                register_count,
                started,
                "error",
                f"{type(error).__name__}: {error}",
                sensitive_response,
                "read_holding_registers",
            )
            raise
        self._record(
            request,
            response,
            start_register,
            register_count,
            started,
            "ok",
            None,
            sensitive_response,
            "read_holding_registers",
        )
        return registers

    def _write_single_register(self, register: int, value: int) -> None:
        request = WriteSingleRegisterRequest(self._slave_address, register, value).to_frame()
        response = b""
        started = time.monotonic()
        try:
            response = self._transport.exchange(request)
            parse_write_single_response(
                response,
                expected_address=self._slave_address,
                expected_register=register,
                expected_value=value,
            )
        except Exception as error:
            if isinstance(error, ResponseTimeoutError):
                response = error.partial_response
            self._record(
                request,
                response,
                register,
                1,
                started,
                "error",
                f"{type(error).__name__}: {error}",
                False,
                "write_single_register",
            )
            raise
        self._record(
            request,
            response,
            register,
            1,
            started,
            "ok",
            None,
            False,
            "write_single_register",
        )

    def _write_multiple_registers(self, start_register: int, values: tuple[int, ...]) -> None:
        request = WriteMultipleRegistersRequest(
            self._slave_address, start_register, values
        ).to_frame()
        response = b""
        started = time.monotonic()
        try:
            response = self._transport.exchange(request)
            parse_write_multiple_response(
                response,
                expected_address=self._slave_address,
                expected_start_register=start_register,
                expected_count=len(values),
            )
        except Exception as error:
            if isinstance(error, ResponseTimeoutError):
                response = error.partial_response
            self._record(
                request,
                response,
                start_register,
                len(values),
                started,
                "error",
                f"{type(error).__name__}: {error}",
                False,
                "write_multiple_registers",
            )
            raise
        self._record(
            request,
            response,
            start_register,
            len(values),
            started,
            "ok",
            None,
            False,
            "write_multiple_registers",
        )

    def read_identity(self) -> DeviceIdentity:
        registers = self.read_holding_registers(
            IDENTITY_START, IDENTITY_COUNT, sensitive_response=True
        )
        return decode_identity(registers)

    def test_connection(self) -> DeviceIdentity:
        identity = self.read_identity()
        if identity.model not in SUPPORTED_INTERNAL_MODELS:
            raise UnsupportedDeviceError(
                f"unsupported model {identity.model!r}; expected one of "
                f"{sorted(SUPPORTED_INTERNAL_MODELS)}"
            )
        if identity.configured_address != self._slave_address:
            raise UnsupportedDeviceError(
                f"identity reports address {identity.configured_address}, "
                f"but the request used {self._slave_address}"
            )
        return identity

    def read_realtime(self) -> RealtimeSnapshot:
        return decode_realtime(self.read_holding_registers(REALTIME_START, REALTIME_COUNT))

    def read_remote_enabled(self) -> bool:
        value = self.read_holding_registers(REMOTE_OUTPUT_REGISTER, 1)[0]
        if value not in {0, 1}:
            raise UnsupportedDeviceError(
                f"remote-output register contains unsupported value {value}"
            )
        return value == 0

    def read_terminal_setpoints(self, terminal: str) -> TerminalSetpoints:
        start = self._terminal_settings_start(terminal)
        return decode_terminal_setpoints(
            self.read_holding_registers(start, TERMINAL_SETTINGS_COUNT)
        )

    def read_control_settings(self) -> ControlSettings:
        return ControlSettings(
            remote_enabled=self.read_remote_enabled(),
            terminal_a=self.read_terminal_setpoints("A"),
            terminal_b=self.read_terminal_setpoints("B"),
        )

    def write_remote_enabled(self, enabled: bool) -> None:
        self._write_single_register(REMOTE_OUTPUT_REGISTER, 0 if enabled else 1)

    def write_terminal_voltage(self, terminal: str, voltage_v: float) -> None:
        self._write_terminal_scaled_value(terminal, 0, voltage_v)

    def write_terminal_current(self, terminal: str, current_a: float) -> None:
        self._write_terminal_scaled_value(terminal, 1, current_a)

    def _write_terminal_scaled_value(self, terminal: str, offset: int, value: float) -> None:
        raw_value = round(value * 100)
        if not 0 <= raw_value <= 0xFFFF or abs(value - raw_value / 100) > 1e-9:
            raise ValueError("scaled terminal setting must fit an unsigned 16-bit register")
        self._write_single_register(self._terminal_settings_start(terminal) + offset, raw_value)

    @staticmethod
    def _terminal_settings_start(terminal: str) -> int:
        if terminal == "A":
            return TERMINAL_A_SETTINGS_START
        if terminal == "B":
            return TERMINAL_B_SETTINGS_START
        raise ValueError("terminal must be A or B")

    def _record(
        self,
        tx: bytes,
        rx: bytes,
        start_register: int,
        register_count: int,
        started: float,
        result: str,
        error: str | None,
        sensitive_response: bool,
        function: str,
    ) -> None:
        if self._capture is None:
            return
        self._capture.record(
            tx=tx,
            rx=rx,
            start_register=start_register,
            register_count=register_count,
            duration_ms=(time.monotonic() - started) * 1000,
            result=result,
            error=error,
            sensitive_response=sensitive_response,
            function=function,
        )
