#!/usr/bin/env python3
"""Keep time on RTC-less Venus OS systems synchronized via SNTP."""

from __future__ import annotations

import json
import os
import socket
import struct
import time
from datetime import UTC, datetime
from pathlib import Path

NTP_EPOCH_OFFSET = 2_208_988_800
NTP_REQUEST = b"\x23" + (47 * b"\0")
MINIMUM_VALID_EPOCH = 1_735_689_600  # 2025-01-01T00:00:00Z

SERVERS = tuple(
    value.strip()
    for value in os.environ.get(
        "VENUS_TIME_SERVERS",
        "0.europe.pool.ntp.org,1.europe.pool.ntp.org,"
        "2.europe.pool.ntp.org,3.europe.pool.ntp.org",
    ).split(",")
    if value.strip()
)
STATE_DIR = Path(os.environ.get("VENUS_TIME_STATE_DIR", "/data/var/lib/venus-time-sync"))
STATE_FILE = STATE_DIR / "last-known-time.json"
QUERY_TIMEOUT = float(os.environ.get("VENUS_TIME_QUERY_TIMEOUT", "4"))
SYNC_INTERVAL = float(os.environ.get("VENUS_TIME_SYNC_INTERVAL", "900"))
RETRY_INTERVAL = float(os.environ.get("VENUS_TIME_RETRY_INTERVAL", "30"))
SET_THRESHOLD = float(os.environ.get("VENUS_TIME_SET_THRESHOLD", "0.5"))


def log(message: str) -> None:
    print(message, flush=True)


def isoformat(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat()


def median(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def query_sntp(server: str, timeout: float = QUERY_TIMEOUT) -> tuple[float, float]:
    """Return clock offset and round-trip time from one NTP server."""

    addresses = socket.getaddrinfo(server, 123, type=socket.SOCK_DGRAM)
    last_error: Exception | None = None
    for family, socktype, protocol, _, address in addresses:
        sock = socket.socket(family, socktype, protocol)
        sock.settimeout(timeout)
        try:
            started = time.monotonic()
            sock.sendto(NTP_REQUEST, address)
            response, _ = sock.recvfrom(512)
            local_received = time.time()
            elapsed = time.monotonic() - started
        except OSError as exc:
            last_error = exc
            continue
        finally:
            sock.close()

        if len(response) < 48:
            last_error = ValueError(f"short NTP response ({len(response)} bytes)")
            continue

        leap = response[0] >> 6
        mode = response[0] & 0x07
        stratum = response[1]
        if leap == 3 or mode not in {4, 5} or not 1 <= stratum <= 15:
            last_error = ValueError(
                f"invalid NTP status (leap={leap}, mode={mode}, stratum={stratum})"
            )
            continue

        seconds, fraction = struct.unpack("!II", response[40:48])
        epoch = seconds - NTP_EPOCH_OFFSET + fraction / 2**32 + elapsed / 2
        if epoch < MINIMUM_VALID_EPOCH:
            last_error = ValueError(f"implausible NTP timestamp {epoch}")
            continue
        return epoch - local_received, elapsed

    if last_error is None:
        raise OSError(f"no address available for {server}")
    raise last_error


def get_network_time() -> tuple[float, list[str]]:
    offsets: list[float] = []
    sources: list[str] = []
    errors: list[str] = []

    for server in SERVERS:
        try:
            offset, elapsed = query_sntp(server)
        except (OSError, ValueError) as exc:
            errors.append(f"{server}: {exc}")
            continue
        offsets.append(offset)
        sources.append(f"{server} ({elapsed * 1000:.0f} ms)")

    if not offsets:
        raise OSError("; ".join(errors) or "no NTP servers configured")

    median_offset = median(offsets)
    close_offsets = [offset for offset in offsets if abs(offset - median_offset) <= 5]
    if not close_offsets:
        raise ValueError("NTP replies disagree")
    return time.time() + median(close_offsets), sources


def set_clock(epoch: float) -> float:
    previous = time.time()
    offset = epoch - previous
    if abs(offset) >= SET_THRESHOLD:
        time.clock_settime(time.CLOCK_REALTIME, epoch)
    return offset


def save_last_known_time(epoch: float) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"epoch": int(epoch), "utc": isoformat(epoch)}) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, STATE_FILE)


def restore_lower_bound() -> None:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        saved_epoch = float(state["epoch"])
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return

    current = time.time()
    if saved_epoch >= MINIMUM_VALID_EPOCH and current < saved_epoch:
        time.clock_settime(time.CLOCK_REALTIME, saved_epoch)
        log(f"restored persistent lower time bound {isoformat(saved_epoch)}")


def main() -> None:
    if not SERVERS:
        raise SystemExit("VENUS_TIME_SERVERS must contain at least one server")

    restore_lower_bound()
    while True:
        try:
            network_epoch, sources = get_network_time()
            offset = set_clock(network_epoch)
            now = time.time()
            save_last_known_time(now)
            log(
                f"synchronized {isoformat(now)}; offset={offset:+.3f}s; "
                f"sources={', '.join(sources)}"
            )
            delay = SYNC_INTERVAL
        except (OSError, ValueError, PermissionError) as exc:
            log(f"synchronization failed: {exc}; retrying in {RETRY_INTERVAL:.0f}s")
            delay = RETRY_INTERVAL
        time.sleep(delay)


if __name__ == "__main__":
    main()
