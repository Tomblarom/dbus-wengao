"""Generate isolated daemontools services for enabled device instances."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from wengao.config import load_config
from wengao.errors import ConfigurationError
from wengao.venus.portlock import TTY_PATTERN

DEFAULT_APP_ROOT = Path("/data/apps/dbus-wengao")
DEFAULT_CONFIG = Path("/data/setupOptions/WengaoDcdc/config.toml")
DEFAULT_LINK_ROOT = Path("/service")
SERIAL_STARTER_STOP = Path("/opt/victronenergy/serial-starter/stop-tty.sh")
SERIAL_STARTER_STOP_TIMEOUT = 5.0
SUPERVISOR_EXIT_TIMEOUT = 5.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate dbus-wengao daemontools services")
    parser.add_argument("--app-root", type=Path, default=DEFAULT_APP_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--link-root", type=Path, default=DEFAULT_LINK_ROOT)
    parser.add_argument("--disable", action="store_true")
    parser.add_argument("--no-links", action="store_true", help=argparse.SUPPRESS)
    return parser


def generate_services(
    *,
    app_root: Path,
    config_path: Path,
    link_root: Path | None,
) -> tuple[str, ...]:
    app_root = app_root.resolve()
    template_root = app_root / "service"
    run_template = template_root / "run"
    log_template = template_root / "log" / "run"
    if not run_template.is_file() or not log_template.is_file():
        raise ConfigurationError(f"service templates are missing under {template_root}")
    config = load_config(config_path, require_ports_exist=False)
    generated_root = app_root / "generated-services"
    generated_root.mkdir(mode=0o755, parents=True, exist_ok=True)
    names: list[str] = []
    for device in config.enabled_devices():
        name = f"dbus-wengao.{device.id}"
        service_root = generated_root / name
        log_root = service_root / "log"
        log_root.mkdir(mode=0o755, parents=True, exist_ok=True)
        _copy_executable(run_template, service_root / "run")
        _copy_executable(log_template, log_root / "run")
        names.append(name)
    if link_root is not None:
        for device in config.enabled_devices():
            link = link_root / f"dbus-wengao.{device.id}"
            if link.is_symlink() and _points_within(link, generated_root):
                continue
            _quiesce_serial_starter(device.port)
        _synchronise_links(generated_root, link_root, frozenset(names))
    return tuple(names)


def disable_services(*, app_root: Path, link_root: Path) -> tuple[str, ...]:
    generated_root = app_root.resolve() / "generated-services"
    if not link_root.is_dir():
        return ()
    removed: list[str] = []
    for link in link_root.glob("dbus-wengao.*"):
        if not link.is_symlink():
            continue
        if not _points_within(link, generated_root):
            continue
        _stop_service_tree(link)
        link.unlink()
        removed.append(link.name)
    return tuple(sorted(removed))


def _synchronise_links(generated_root: Path, link_root: Path, desired: frozenset[str]) -> None:
    if not link_root.is_dir():
        raise ConfigurationError(f"service link root does not exist: {link_root}")
    for link in link_root.glob("dbus-wengao.*"):
        if link.name in desired:
            continue
        if link.is_symlink() and _points_within(link, generated_root):
            _stop_service_tree(link)
            link.unlink()
    for name in sorted(desired):
        target = generated_root / name
        link = link_root / name
        if link.exists() and not link.is_symlink():
            raise ConfigurationError(f"refusing to replace non-symlink service path: {link}")
        if link.is_symlink():
            if link.resolve() == target.resolve():
                _start(link)
                continue
            _stop_service_tree(link)
            link.unlink()
        link.symlink_to(target, target_is_directory=True)
        _start(link)


def _copy_executable(source: Path, destination: Path) -> None:
    shutil.copyfile(source, destination)
    destination.chmod(0o755)


def _quiesce_serial_starter(
    configured_port: str,
    *,
    helper: Path = SERIAL_STARTER_STOP,
    device_root: Path = Path("/dev"),
) -> bool:
    """Stop existing auto-probes once before the Wengao process owns the port lock."""

    try:
        resolved = Path(configured_port).resolve(strict=True)
    except OSError:
        return False
    if resolved.parent != device_root.resolve() or not TTY_PATTERN.fullmatch(resolved.name):
        return False
    if not helper.is_file() or not os.access(helper, os.X_OK):
        return False
    try:
        result = subprocess.run(
            [os.fspath(helper), resolved.name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=SERIAL_STARTER_STOP_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def _points_within(link: Path, root: Path) -> bool:
    try:
        link.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _stop(service: Path) -> None:
    svc = shutil.which("svc")
    if svc is None:
        return
    subprocess.run(
        [svc, "-dx", os.fspath(service)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if _wait_for_supervisor_exit(service):
        return
    subprocess.run(
        [svc, "-kx", os.fspath(service)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_supervisor_exit(service)


def _stop_service_tree(service: Path) -> None:
    # Stop the producer before its logger, and ask both supervise processes to exit. Merely
    # unlinking the service leaves orphaned log supervisors holding the multilog directory lock.
    _stop(service)
    _stop(service / "log")


def _wait_for_supervisor_exit(service: Path) -> bool:
    svok = shutil.which("svok")
    if svok is None:
        return True
    deadline = time.monotonic() + SUPERVISOR_EXIT_TIMEOUT
    while time.monotonic() < deadline:
        result = subprocess.run(
            [svok, os.fspath(service)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            return True
        time.sleep(0.05)
    return False


def _start(service: Path) -> None:
    svc = shutil.which("svc")
    if svc is None:
        return
    for path in (service / "log", service):
        subprocess.run(
            [svc, "-u", os.fspath(path)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.disable:
            names = disable_services(app_root=arguments.app_root, link_root=arguments.link_root)
            print(f"disabled {len(names)} dbus-wengao service(s)")
        else:
            names = generate_services(
                app_root=arguments.app_root,
                config_path=arguments.config,
                link_root=None if arguments.no_links else arguments.link_root,
            )
            print(f"enabled {len(names)} dbus-wengao service(s)")
    except (OSError, ConfigurationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
