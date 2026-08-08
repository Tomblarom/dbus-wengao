"""Late loading of Venus-only Python modules."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from wengao.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class VenusRuntime:
    dbus_main_loop: Any
    glib: Any
    service_class: Any


def load_venus_runtime() -> VenusRuntime:
    candidates = [
        os.environ.get("VELIB_PYTHON_PATH"),
        "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python",
        "/opt/victronenergy/dbus-pump/ext/velib_python",
    ]
    velib_path = next((Path(path) for path in candidates if path and Path(path).is_dir()), None)
    if velib_path is None:
        raise ConfigurationError(
            "velib_python was not found; set VELIB_PYTHON_PATH or run on Venus OS"
        )
    sys.path.insert(0, str(velib_path))
    try:
        dbus_glib = import_module("dbus.mainloop.glib")
        glib = import_module("gi.repository.GLib")
        vedbus = import_module("vedbus")
    except ImportError as error:
        raise ConfigurationError(f"cannot load Venus D-Bus runtime: {error}") from error
    return VenusRuntime(dbus_glib.DBusGMainLoop, glib, vedbus.VeDbusService)
