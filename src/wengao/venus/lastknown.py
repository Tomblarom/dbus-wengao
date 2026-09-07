"""Persistent last-known auxiliary-battery voltage state."""

from __future__ import annotations

import json
import logging
import math
import os
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from wengao.profiles import Terminal

STATE_VERSION = 1
MIN_VOLTAGE = 0.0
MAX_VOLTAGE = 65.0
DEFAULT_FLUSH_INTERVAL = 300.0


@dataclass(frozen=True, slots=True)
class LastKnownVoltage:
    voltage_v: float
    observed_at: int

    def is_valid(self) -> bool:
        return (
            math.isfinite(self.voltage_v)
            and MIN_VOLTAGE <= self.voltage_v <= MAX_VOLTAGE
            and self.observed_at > 0
        )


class LastKnownVoltageStore:
    """Keep one terminal voltage across converter sleep and process restarts.

    Successful polls update memory immediately. The first value and periodic checkpoints are
    persisted, while ``flush()`` records the exact final value when communication is lost. This
    avoids writing the Venus OS data partition on every poll.
    """

    def __init__(
        self,
        state_directory: Path,
        device_id: str,
        terminal: Terminal,
        *,
        flush_interval: float = DEFAULT_FLUSH_INTERVAL,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._path = state_directory / f"{device_id}-auxiliary-{terminal.value.lower()}.json"
        self._flush_interval = flush_interval
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._value: LastKnownVoltage | None = None
        self._persisted: LastKnownVoltage | None = None
        self._last_flush_at: float | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def value(self) -> LastKnownVoltage | None:
        return self._value

    def load(self) -> LastKnownVoltage | None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("version") != STATE_VERSION:
                raise ValueError("unsupported state format")
            value = LastKnownVoltage(float(raw["voltage_v"]), int(raw["observed_at"]))
            if not value.is_valid():
                raise ValueError("state values are outside their valid range")
        except FileNotFoundError:
            return None
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            logging.warning("ignoring invalid last-known voltage state %s: %s", self._path, error)
            return None
        self._value = value
        self._persisted = value
        self._last_flush_at = self._monotonic_clock()
        return value

    def record(self, voltage_v: float, *, observed_at: int | None = None) -> LastKnownVoltage:
        value = LastKnownVoltage(
            float(voltage_v),
            int(self._wall_clock()) if observed_at is None else observed_at,
        )
        if not value.is_valid():
            raise ValueError("last-known voltage values are outside their valid range")
        self._value = value
        return value

    def flush_if_due(self) -> bool:
        if self._value is None or self._value == self._persisted:
            return False
        if (
            self._last_flush_at is not None
            and self._monotonic_clock() - self._last_flush_at < self._flush_interval
        ):
            return False
        return self.flush()

    def flush(self) -> bool:
        if self._value is None or self._value == self._persisted:
            return False
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = {
            "version": STATE_VERSION,
            "voltage_v": self._value.voltage_v,
            "observed_at": self._value.observed_at,
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
            logging.warning("cannot persist last-known voltage state %s: %s", self._path, error)
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            return False
        self._persisted = self._value
        self._last_flush_at = self._monotonic_clock()
        return True
