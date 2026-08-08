from __future__ import annotations

import os
from pathlib import Path

import pytest

from wengao.venus.portlock import SerialStarterPortLock


def environment(tmp_path: Path, *, pid: int = 1234) -> tuple[SerialStarterPortLock, Path, Path]:
    device_root = tmp_path / "dev"
    physical = device_root / "ttyACM1"
    physical.parent.mkdir()
    physical.touch()
    by_path = device_root / "serial" / "by-path" / "synthetic"
    by_path.parent.mkdir(parents=True)
    try:
        by_path.symlink_to(physical)
    except OSError as error:
        pytest.skip(f"platform does not permit unprivileged symlink tests: {error}")
    lock_root = tmp_path / "locks"
    process_root = tmp_path / "proc"
    process_root.mkdir()
    lock = SerialStarterPortLock(
        lock_root=lock_root,
        device_root=device_root,
        process_root=process_root,
        pid=pid,
    )
    return lock, by_path, lock_root


def test_acquires_and_releases_serial_starter_lock(tmp_path: Path) -> None:
    lock, port, lock_root = environment(tmp_path)
    assert lock.acquire_for_port(os.fspath(port))
    path = lock_root / "ttyACM1"
    assert path.is_symlink()
    assert os.readlink(path) == "1234"
    assert lock.tty == "ttyACM1"
    lock.release()
    assert not path.is_symlink()


def test_repeated_acquire_keeps_owned_lock(tmp_path: Path) -> None:
    lock, port, lock_root = environment(tmp_path)
    assert lock.acquire_for_port(os.fspath(port))
    assert lock.acquire_for_port(os.fspath(port))
    assert os.readlink(lock_root / "ttyACM1") == "1234"


def test_does_not_take_lock_from_live_process(tmp_path: Path) -> None:
    lock, port, lock_root = environment(tmp_path)
    (tmp_path / "proc" / "999").mkdir()
    lock_root.mkdir()
    (lock_root / "ttyACM1").symlink_to("999")
    assert not lock.acquire_for_port(os.fspath(port))
    assert os.readlink(lock_root / "ttyACM1") == "999"


def test_replaces_stale_pid_lock(tmp_path: Path) -> None:
    lock, port, lock_root = environment(tmp_path)
    lock_root.mkdir()
    (lock_root / "ttyACM1").symlink_to("999")
    assert lock.acquire_for_port(os.fspath(port))
    assert os.readlink(lock_root / "ttyACM1") == "1234"


def test_does_not_remove_foreign_replacement_on_release(tmp_path: Path) -> None:
    lock, port, lock_root = environment(tmp_path)
    assert lock.acquire_for_port(os.fspath(port))
    path = lock_root / "ttyACM1"
    path.unlink()
    path.symlink_to("5678")
    lock.release()
    assert os.readlink(path) == "5678"


def test_missing_port_is_not_assumed(tmp_path: Path) -> None:
    lock, port, _lock_root = environment(tmp_path)
    port.unlink()
    assert not lock.acquire_for_port(os.fspath(port))


def test_rejects_resolved_path_outside_device_root(tmp_path: Path) -> None:
    lock, _port, _lock_root = environment(tmp_path)
    outside = tmp_path / "ttyACM9"
    outside.touch()
    assert not lock.acquire_for_port(os.fspath(outside))
