"""One read-only Venus service process per configured converter."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import time
from collections.abc import Sequence
from importlib import import_module
from pathlib import Path
from typing import Any, BinaryIO

from wengao.config import DeviceConfig, load_config
from wengao.errors import WengaoError
from wengao.protocol.capture import CaptureWriter
from wengao.protocol.client import WengaoProtocol
from wengao.protocol.transport import SerialRtuTransport
from wengao.venus.portlock import SerialStarterPortLock
from wengao.venus.publisher import VenusPublisher, service_name
from wengao.venus.runtime import load_venus_runtime

DEFAULT_CONFIG = Path("/data/setupOptions/WengaoDcdc/config.toml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one read-only dbus-wengao service")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--device-id", required=True)
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO"
    )
    return parser


def _lock_instance(device_id: str) -> BinaryIO:
    fcntl: Any = import_module("fcntl")

    path = Path(f"/var/tmp/dbus-wengao_{device_id}.pid")
    handle = path.open("a+b")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.close()
        raise RuntimeError(f"another process already owns device {device_id}") from error
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()).encode("ascii"))
    handle.flush()
    return handle


def _capture(config: DeviceConfig, root: Path, enabled: bool) -> CaptureWriter | None:
    if not enabled:
        return None
    return CaptureWriter(root / f"{config.id}.jsonl", device_id=config.id, port_alias=config.id)


def run_service(config_path: Path, device_id: str) -> int:
    driver_config = load_config(config_path, require_ports_exist=False)
    config = driver_config.device(device_id)
    if not config.enabled:
        raise RuntimeError(f"device {device_id!r} is disabled")
    lock = _lock_instance(config.id)
    capture = _capture(
        config,
        Path(driver_config.debug.capture_directory),
        driver_config.debug.raw_capture,
    )
    transport = SerialRtuTransport(
        config.port,
        timeout=config.communication_timeout,
    )
    protocol = WengaoProtocol(
        transport,
        slave_address=config.slave_address,
        capture=capture,
    )
    identity = None
    snapshot = None
    backoff = 1.0
    port_lock = SerialStarterPortLock()
    while identity is None or snapshot is None:
        if not port_lock.acquire_for_port(config.port):
            logging.warning("waiting for exclusive serial-starter lock for %s", config.id)
            time.sleep(min(backoff, 5))
            backoff = min(backoff * 2, 30)
            continue
        try:
            identity = protocol.test_connection()
            snapshot = protocol.read_realtime()
        except (OSError, WengaoError) as error:
            logging.warning("initial read failed for %s: %s", config.id, error)
            transport.close()
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
    runtime = load_venus_runtime()
    runtime.dbus_main_loop(set_as_default=True)
    backend = runtime.service_class(service_name(config), register=False)
    publisher = VenusPublisher(backend, config, identity)
    publisher.publish(snapshot)
    main_loop = runtime.glib.MainLoop()
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        main_loop.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def poll() -> bool:
        if stopping:
            return False
        if not port_lock.acquire_for_port(config.port):
            transport.close()
            publisher.mark_disconnected()
            logging.warning("serial port or serial-starter lock unavailable for %s", config.id)
            return True
        try:
            current = protocol.read_realtime()
            if current.plausibility_errors():
                raise RuntimeError("; ".join(current.plausibility_errors()))
            publisher.publish(current)
        except (OSError, WengaoError, RuntimeError) as error:
            logging.warning("poll failed for %s: %s", config.id, error)
            transport.close()
            publisher.mark_disconnected()
        return True

    runtime.glib.timeout_add(int(config.poll_interval * 1000), poll)
    try:
        main_loop.run()
    finally:
        transport.close()
        port_lock.release()
        lock.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, arguments.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        return run_service(arguments.config, arguments.device_id)
    except (OSError, RuntimeError, WengaoError) as error:
        logging.error("service stopped: %s", error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
