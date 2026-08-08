"""Cooperate with Venus serial-starter without changing its global aliases."""

from __future__ import annotations

import os
import re
from pathlib import Path

TTY_PATTERN = re.compile(r"^tty[A-Za-z0-9_.-]+$")


class SerialStarterPortLock:
    """Own the same per-TTY lock that serial-starter uses while this process runs."""

    def __init__(
        self,
        *,
        lock_root: Path = Path("/var/lock/serial-starter"),
        device_root: Path = Path("/dev"),
        process_root: Path = Path("/proc"),
        pid: int | None = None,
    ) -> None:
        self._lock_root = lock_root
        self._device_root = device_root.resolve()
        self._process_root = process_root
        self._pid = os.getpid() if pid is None else pid
        self._owned: Path | None = None

    @property
    def tty(self) -> str | None:
        return self._owned.name if self._owned else None

    def acquire_for_port(self, configured_port: str) -> bool:
        try:
            resolved = Path(configured_port).resolve(strict=True)
        except OSError:
            return False
        if resolved.parent != self._device_root or not TTY_PATTERN.fullmatch(resolved.name):
            return False
        desired = self._lock_root / resolved.name
        if self._owned == desired and self._is_ours(desired):
            return True
        if self._owned is not None:
            self.release()
        self._lock_root.mkdir(mode=0o755, parents=True, exist_ok=True)
        if self._create(desired):
            self._owned = desired
            return True
        if self._remove_stale(desired) and self._create(desired):
            self._owned = desired
            return True
        return False

    def release(self) -> None:
        if self._owned is not None and self._is_ours(self._owned):
            self._owned.unlink()
        self._owned = None

    def _create(self, path: Path) -> bool:
        try:
            path.symlink_to(str(self._pid))
        except FileExistsError:
            return False
        return True

    def _remove_stale(self, path: Path) -> bool:
        if not path.is_symlink():
            return False
        try:
            owner = os.readlink(path)
            owner_pid = int(owner)
        except (OSError, ValueError):
            return False
        if (self._process_root / str(owner_pid)).exists():
            return False
        try:
            if os.readlink(path) != owner:
                return False
            path.unlink()
        except OSError:
            return False
        return True

    def _is_ours(self, path: Path) -> bool:
        try:
            return path.is_symlink() and os.readlink(path) == str(self._pid)
        except OSError:
            return False

    def __enter__(self) -> SerialStarterPortLock:
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()
