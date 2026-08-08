"""Privacy-aware JSON Lines communication capture."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any


class CaptureWriter:
    def __init__(self, path: Path, *, device_id: str, port_alias: str) -> None:
        self._path = path
        self._device_id = device_id
        self._port_alias = port_alias
        self._lock = threading.Lock()

    def record(
        self,
        *,
        tx: bytes,
        rx: bytes,
        start_register: int,
        register_count: int,
        duration_ms: float,
        result: str,
        error: str | None = None,
        sensitive_response: bool = False,
    ) -> None:
        record: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "device": self._device_id,
            "port": self._port_alias,
            "tx_hex": tx.hex().upper(),
            "decoded": {
                "function": "read_holding_registers",
                "start_register": f"0x{start_register:04X}",
                "register_count": register_count,
            },
            "duration_ms": round(duration_ms, 3),
            "result": result,
        }
        if sensitive_response:
            record["rx_hex"] = None
            record["rx_redacted"] = True
            record["rx_sha256"] = sha256(rx).hexdigest() if rx else None
        else:
            record["rx_hex"] = rx.hex().upper()
        if error:
            record["error"] = error
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
