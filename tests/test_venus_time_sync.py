from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


def load_module() -> ModuleType:
    path = Path(__file__).parents[1] / "contrib" / "venus-time-sync" / "time_sync.py"
    spec = importlib.util.spec_from_file_location("venus_time_sync", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_median_supports_odd_and_even_sample_counts() -> None:
    module = load_module()

    assert module.median([3.0, 1.0, 2.0]) == 2.0
    assert module.median([4.0, 1.0, 3.0, 2.0]) == 2.5


def test_network_time_uses_consistent_median_offsets(monkeypatch) -> None:
    module = load_module()
    module.SERVERS = ("one", "two", "outlier")
    replies = iter(((10.0, 0.1), (10.2, 0.2), (500.0, 0.3)))
    monkeypatch.setattr(module, "query_sntp", lambda _server: next(replies))
    monkeypatch.setattr(module.time, "time", lambda: 1_000.0)

    epoch, sources = module.get_network_time()

    assert epoch == 1_010.1
    assert len(sources) == 3


def test_restore_lower_bound_never_moves_clock_backwards(monkeypatch, tmp_path: Path) -> None:
    module = load_module()
    module.STATE_FILE = tmp_path / "last-known-time.json"
    module.STATE_FILE.write_text(json.dumps({"epoch": 1_800_000_000}), encoding="utf-8")
    changed_to: list[float] = []
    monkeypatch.setattr(module.time, "CLOCK_REALTIME", 0, raising=False)
    monkeypatch.setattr(
        module.time,
        "clock_settime",
        lambda _clock, value: changed_to.append(value),
        raising=False,
    )

    monkeypatch.setattr(module.time, "time", lambda: 1_700_000_000)
    module.restore_lower_bound()
    assert changed_to == [1_800_000_000]

    changed_to.clear()
    monkeypatch.setattr(module.time, "time", lambda: 1_900_000_000)
    module.restore_lower_bound()
    assert changed_to == []
