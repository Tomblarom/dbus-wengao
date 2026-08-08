"""Read-only Wengao protocol client."""

from __future__ import annotations

import time
from typing import Protocol

from wengao.errors import ResponseTimeoutError, UnsupportedDeviceError
from wengao.model import DeviceIdentity, RealtimeSnapshot

from .capture import CaptureWriter
from .frame import ReadHoldingRequest, parse_read_holding_response
from .registers import (
    IDENTITY_COUNT,
    IDENTITY_START,
    REALTIME_COUNT,
    REALTIME_START,
    decode_identity,
    decode_realtime,
)


class Transport(Protocol):
    def exchange(self, request: bytes) -> bytes: ...


SUPPORTED_INTERNAL_MODELS = frozenset({"WG-BC1500M", "WG-48BC1500M"})


class WengaoProtocol:
    """The public API intentionally contains no Modbus write operation."""

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
        )
        return registers

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
        )
