"""Explicit, bounded writes with response validation and device readback."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

from wengao.config import DeviceConfig, WriteRange
from wengao.errors import UnsafeWriteError
from wengao.model import ControlSettings, DeviceIdentity, TerminalSetpoints
from wengao.profiles import Direction, Terminal
from wengao.protocol.client import SUPPORTED_INTERNAL_MODELS


class ControlProtocol(Protocol):
    def read_control_settings(self) -> ControlSettings: ...

    def read_remote_enabled(self) -> bool: ...

    def read_terminal_setpoints(self, terminal: str) -> TerminalSetpoints: ...

    def write_remote_enabled(self, enabled: bool) -> None: ...

    def write_terminal_voltage(self, terminal: str, voltage_v: float) -> None: ...

    def write_terminal_current(self, terminal: str, current_a: float) -> None: ...


class SafeWriteController:
    """The only layer allowed to turn a D-Bus request into a Modbus write."""

    def __init__(
        self,
        protocol: ControlProtocol,
        config: DeviceConfig,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._protocol = protocol
        self._config = config
        self._monotonic = monotonic
        self._identity_verified = False
        self._last_write_at: dict[str, float] = {}
        self._last_verified: ControlSettings | None = None

    @property
    def identity_verified(self) -> bool:
        return self._identity_verified

    def authorize_identity(self, identity: DeviceIdentity) -> None:
        self._identity_verified = (
            identity.model in SUPPORTED_INTERNAL_MODELS
            and identity.configured_address == self._config.slave_address
        )
        if not self._identity_verified:
            raise UnsafeWriteError("device identity does not match the validated configuration")

    def revoke(self) -> None:
        self._identity_verified = False

    def read_settings(self) -> ControlSettings:
        self._require_verified_device()
        try:
            settings = self._protocol.read_control_settings()
        except Exception:
            # A failed read makes the device identity and its current state uncertain.  Require
            # the normal connection/identity handshake before accepting another write.
            self.revoke()
            raise
        self._last_verified = settings
        return settings

    def set_remote_enabled(self, enabled: bool) -> ControlSettings:
        self._require_verified_device()
        if not self._config.permissions.remote_on_off:
            raise UnsafeWriteError("remote on/off permission is disabled")
        current = self.read_settings()
        if current.remote_enabled == enabled:
            return current
        self._check_rate_limit("remote")
        # Start the rate-limit window before sending.  A timeout may mean that the persistent
        # register was changed even though its response or readback was lost.
        self._record_write("remote")
        try:
            self._protocol.write_remote_enabled(enabled)
            verified_enabled = self._protocol.read_remote_enabled()
        except Exception:
            self.revoke()
            raise
        if verified_enabled != enabled:
            self.revoke()
            raise UnsafeWriteError("remote on/off readback does not match the request")
        verified = replace(current, remote_enabled=verified_enabled)
        self._last_verified = verified
        return verified

    def set_voltage(self, terminal: Terminal, voltage_v: float) -> ControlSettings:
        if not self._config.permissions.set_voltage:
            raise UnsafeWriteError("voltage-setpoint permission is disabled")
        limit = self._required_limit(terminal, "voltage")
        raw_value = self._validate_scaled_value(voltage_v, limit, "voltage")
        return self._set_terminal_value(terminal, "voltage", raw_value)

    def set_current(self, terminal: Terminal, current_a: float) -> ControlSettings:
        if not self._config.permissions.set_current:
            raise UnsafeWriteError("current-setpoint permission is disabled")
        limit = self._required_limit(terminal, "current")
        raw_value = self._validate_scaled_value(current_a, limit, "current")
        return self._set_terminal_value(terminal, "current", raw_value)

    def _set_terminal_value(
        self, terminal: Terminal, kind: str, raw_value: int
    ) -> ControlSettings:
        self._require_verified_device()
        self._require_destination_terminal(terminal)
        current = self.read_settings()
        terminal_settings = self._terminal_settings(current, terminal)
        requested_value = raw_value / 100
        existing_value = (
            terminal_settings.voltage_v if kind == "voltage" else terminal_settings.current_a
        )
        if round(existing_value * 100) == raw_value:
            return current
        key = f"terminal-{terminal.value}"
        self._check_rate_limit(key)
        # Record the attempt before touching the persistent setpoint register.  This also
        # throttles retries after an ambiguous timeout.
        self._record_write(key)
        if kind == "voltage":
            requested = replace(terminal_settings, voltage_v=requested_value)
        else:
            requested = replace(terminal_settings, current_a=requested_value)

        # The Android manufacturer app writes ordinary voltage/current edits individually with
        # function 0x06. This avoids rewriting the two other persistent registers.
        try:
            if kind == "voltage":
                self._protocol.write_terminal_voltage(terminal.value, requested.voltage_v)
            else:
                self._protocol.write_terminal_current(terminal.value, requested.current_a)
            verified_terminal = self._protocol.read_terminal_setpoints(terminal.value)
        except Exception:
            self.revoke()
            raise
        if verified_terminal != requested:
            self.revoke()
            raise UnsafeWriteError(
                f"terminal {terminal.value} setpoint readback does not match the request"
            )
        verified = (
            replace(current, terminal_a=verified_terminal)
            if terminal is Terminal.A
            else replace(current, terminal_b=verified_terminal)
        )
        self._last_verified = verified
        return verified

    def _require_verified_device(self) -> None:
        if not self._identity_verified:
            raise UnsafeWriteError("writes are locked until the device identity is verified")

    def _require_destination_terminal(self, terminal: Terminal) -> None:
        destination_directions = {
            Terminal.B: Direction.A_TO_B,
            Terminal.A: Direction.B_TO_A,
        }
        if destination_directions[terminal] not in self._config.allowed_directions:
            raise UnsafeWriteError(
                f"terminal {terminal.value} is not a destination in any allowed direction"
            )

    def _required_limit(self, terminal: Terminal, kind: str) -> WriteRange:
        limit = (
            self._config.write_limits.voltage(terminal)
            if kind == "voltage"
            else self._config.write_limits.current(terminal)
        )
        if limit is None:
            raise UnsafeWriteError(
                f"no configured {kind} write range for terminal {terminal.value}"
            )
        return limit

    @staticmethod
    def _validate_scaled_value(value: float, limit: WriteRange, kind: str) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise UnsafeWriteError(f"{kind} must be numeric")
        numeric = float(value)
        raw_value = round(numeric * 100)
        normalized = raw_value / 100
        if abs(numeric - normalized) > 1e-9:
            raise UnsafeWriteError(f"{kind} supports at most two decimal places")
        if not limit.contains(normalized):
            raise UnsafeWriteError(
                f"{kind} {normalized:g} is outside configured range "
                f"{limit.minimum:g}..{limit.maximum:g}"
            )
        return raw_value

    def _check_rate_limit(self, key: str) -> None:
        previous = self._last_write_at.get(key)
        if previous is None:
            return
        remaining = self._config.write_limits.minimum_interval - (
            self._monotonic() - previous
        )
        if remaining > 0:
            raise UnsafeWriteError(f"write rate limit active for another {remaining:.1f} seconds")

    def _record_write(self, key: str) -> None:
        self._last_write_at[key] = self._monotonic()

    @staticmethod
    def _terminal_settings(settings: ControlSettings, terminal: Terminal) -> TerminalSetpoints:
        return settings.terminal_a if terminal is Terminal.A else settings.terminal_b
