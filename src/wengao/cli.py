"""Read-only command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from wengao.errors import WengaoError
from wengao.protocol.capture import CaptureWriter
from wengao.protocol.client import WengaoProtocol
from wengao.protocol.transport import SerialRtuTransport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbus-wengao-read",
        description="Read a WG-48BC1500M over Modbus RTU without writing device registers.",
    )
    parser.add_argument("--port", required=True, help="Serial device to open")
    parser.add_argument("--slave-address", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--count", type=int, default=1, help="Snapshots to read; 0 means forever")
    parser.add_argument("--once", action="store_true", help="Explicit alias for --count 1")
    parser.add_argument("--capture", type=Path, help="Optional privacy-aware JSONL capture")
    parser.add_argument(
        "--device-id", default="wengao-device", help="Non-identifying device label for captures"
    )
    parser.add_argument(
        "--port-alias", default="serial-port", help="Non-identifying port label for captures"
    )
    return parser


def run(arguments: argparse.Namespace) -> int:
    count = 1 if arguments.once else arguments.count
    if count < 0:
        raise ValueError("count must not be negative")
    if arguments.interval <= 0:
        raise ValueError("interval must be positive")
    capture = (
        CaptureWriter(
            arguments.capture,
            device_id=arguments.device_id,
            port_alias=arguments.port_alias,
        )
        if arguments.capture
        else None
    )
    with SerialRtuTransport(arguments.port, timeout=arguments.timeout) as transport:
        protocol = WengaoProtocol(transport, slave_address=arguments.slave_address, capture=capture)
        identity = protocol.test_connection()
        print(json.dumps({"identity": identity.safe_mapping()}, sort_keys=True))
        completed = 0
        while count == 0 or completed < count:
            snapshot = protocol.read_realtime()
            result = snapshot.safe_mapping()
            result["plausibility_errors"] = list(snapshot.plausibility_errors())
            print(json.dumps({"realtime": result}, sort_keys=True))
            completed += 1
            if count == 0 or completed < count:
                time.sleep(arguments.interval)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        return run(arguments)
    except (OSError, ValueError, WengaoError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
