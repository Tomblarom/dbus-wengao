"""Serial RTU transport; it has no knowledge of Wengao registers or Venus OS."""

from __future__ import annotations

import threading
import time
from types import TracebackType

import serial

from wengao.errors import ResponseTimeoutError


class SerialRtuTransport:
    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 9600,
        timeout: float = 1.0,
        silent_interval: float = 0.01,
    ) -> None:
        if baudrate != 9600:
            raise ValueError("WG-48BC1500M communication is currently verified only at 9600 baud")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.port = port
        self.timeout = timeout
        self._baudrate = baudrate
        self._silent_interval = silent_interval
        self._serial: serial.Serial | None = None
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def open(self) -> None:
        if self.is_open:
            return
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self._baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            write_timeout=self.timeout,
            exclusive=True,
        )

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def exchange(self, request: bytes) -> bytes:
        with self._lock:
            self.open()
            assert self._serial is not None
            self._serial.reset_input_buffer()
            self._serial.write(request)
            self._serial.flush()
            response = bytearray()
            response.extend(self._read_exact(2, response))
            if response[1] & 0x80:
                response.extend(self._read_exact(3, response))
            else:
                response.extend(self._read_exact(1, response))
                response.extend(self._read_exact(response[2] + 2, response))
            waiting = self._serial.in_waiting
            if waiting:
                response.extend(self._serial.read(waiting))
            time.sleep(self._silent_interval)
            return bytes(response)

    def _read_exact(self, count: int, partial: bytearray) -> bytes:
        assert self._serial is not None
        data = self._serial.read(count)
        if len(data) != count:
            received = bytes(partial) + data
            raise ResponseTimeoutError(
                f"serial timeout after {len(received)} response bytes", partial_response=received
            )
        return data

    def __enter__(self) -> SerialRtuTransport:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
