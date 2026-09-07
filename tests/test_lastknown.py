from __future__ import annotations

import json
import os
from pathlib import Path

from wengao.profiles import Terminal
from wengao.venus.lastknown import LastKnownVoltageStore


def test_last_known_voltage_round_trip(tmp_path: Path) -> None:
    store = LastKnownVoltageStore(
        tmp_path,
        "vehicle-link",
        Terminal.A,
        wall_clock=lambda: 1_700_000_000,
        monotonic_clock=lambda: 10.0,
    )
    assert store.load() is None
    value = store.record(12.63)
    assert value.voltage_v == 12.63
    assert value.observed_at == 1_700_000_000
    assert store.flush()
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600

    restored = LastKnownVoltageStore(
        tmp_path,
        "vehicle-link",
        Terminal.A,
        monotonic_clock=lambda: 20.0,
    ).load()
    assert restored == value


def test_last_known_voltage_store_limits_periodic_writes(tmp_path: Path) -> None:
    monotonic = [10.0]
    store = LastKnownVoltageStore(
        tmp_path,
        "vehicle-link",
        Terminal.A,
        flush_interval=300.0,
        monotonic_clock=lambda: monotonic[0],
    )
    store.record(12.5, observed_at=1_700_000_000)
    assert store.flush_if_due()
    store.record(12.6, observed_at=1_700_000_010)
    monotonic[0] = 100.0
    assert not store.flush_if_due()
    monotonic[0] = 311.0
    assert store.flush_if_due()


def test_invalid_last_known_voltage_state_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "vehicle-link-auxiliary-a.json"
    path.write_text(json.dumps({"version": 1, "voltage_v": 99, "observed_at": 1}), encoding="utf-8")
    store = LastKnownVoltageStore(tmp_path, "vehicle-link", Terminal.A)
    assert store.load() is None
    assert store.value is None
