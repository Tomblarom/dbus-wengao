"""One isolated Venus service process per configured converter."""

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

from wengao.config import DeviceConfig, UnavailableDeviceDisplay, load_config
from wengao.control import SafeWriteController
from wengao.errors import WengaoError
from wengao.profiles import ControlMode
from wengao.protocol.capture import CaptureWriter
from wengao.protocol.client import WengaoProtocol
from wengao.protocol.transport import SerialRtuTransport
from wengao.venus.portlock import SerialStarterPortLock
from wengao.venus.publisher import (
    AuxiliaryBatteryPublisher,
    VenusPublisher,
    auxiliary_battery_service_name,
    service_name,
)
from wengao.venus.runtime import load_venus_runtime

DEFAULT_CONFIG = Path("/data/setupOptions/WengaoDcdc/config.toml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one safety-gated dbus-wengao service")
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
    controller = SafeWriteController(protocol, config)
    runtime = load_venus_runtime()
    runtime.dbus_main_loop(set_as_default=True)
    show_unavailable = driver_config.display.unavailable_devices is UnavailableDeviceDisplay.ZERO
    publisher: VenusPublisher | None = None
    if show_unavailable:
        backend = runtime.service_class(service_name(config), register=False)
        publisher = VenusPublisher(
            backend,
            config,
            None,
            show_unavailable=True,
            controller=controller,
        )
    auxiliary_publisher: AuxiliaryBatteryPublisher | None = None
    auxiliary = config.auxiliary_battery
    if auxiliary is not None and auxiliary.enabled:
        auxiliary_backend = runtime.service_class(
            auxiliary_battery_service_name(config), register=False
        )
        auxiliary_publisher = AuxiliaryBatteryPublisher(
            auxiliary_backend,
            config,
            None,
            show_unavailable=show_unavailable,
        )

    main_loop = runtime.glib.MainLoop()
    stopping = False
    identity = None
    port_lock = SerialStarterPortLock()
    backoff = 1.0
    next_attempt_at = 0.0
    next_control_read_at = 0.0

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        main_loop.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def mark_disconnected() -> None:
        controller.revoke()
        if publisher is not None:
            publisher.mark_disconnected()
        if auxiliary_publisher is not None:
            auxiliary_publisher.mark_disconnected()

    def poll() -> bool:
        nonlocal identity, publisher, backoff, next_attempt_at, next_control_read_at
        if stopping:
            return False
        now = time.monotonic()
        if now < next_attempt_at:
            return True
        if not port_lock.acquire_for_port(config.port):
            transport.close()
            identity = None
            mark_disconnected()
            logging.warning("serial port or serial-starter lock unavailable for %s", config.id)
            next_attempt_at = now + backoff
            backoff = min(backoff * 2, 30)
            return True
        try:
            connecting = identity is None
            current_identity = identity or protocol.test_connection()
            if connecting:
                controller.authorize_identity(current_identity)
            current = protocol.read_realtime()
            if current.plausibility_errors():
                raise RuntimeError("; ".join(current.plausibility_errors()))
            identity = current_identity
            if publisher is None:
                backend = runtime.service_class(service_name(config), register=False)
                publisher = VenusPublisher(
                    backend,
                    config,
                    current_identity,
                    show_unavailable=False,
                    controller=controller,
                )
            else:
                publisher.publish_identity(current_identity)
            publisher.publish(current)
            if config.control_mode is ControlMode.EXTERNAL_DBUS and (
                connecting or now >= next_control_read_at
            ):
                publisher.publish_control(controller.read_settings())
                next_control_read_at = now + 30.0
            if auxiliary_publisher is not None:
                auxiliary_publisher.publish_identity(current_identity)
                auxiliary_publisher.publish(current)
            backoff = 1.0
            next_attempt_at = now + config.poll_interval
        except (OSError, WengaoError, RuntimeError) as error:
            logging.warning("poll failed for %s: %s", config.id, error)
            transport.close()
            identity = None
            mark_disconnected()
            next_attempt_at = now + backoff
            backoff = min(backoff * 2, 30)
        return True

    runtime.glib.timeout_add(500, poll)
    try:
        poll()
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
