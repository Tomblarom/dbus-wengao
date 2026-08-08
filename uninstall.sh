#!/bin/bash
set -euo pipefail

APP_ROOT="${DBUS_WENGAO_ROOT:-/data/apps/dbus-wengao}"
EXPECTED_ROOT="/data/apps/dbus-wengao"
RC_LOCAL="/data/rc.local"
BOOT_MARKER="# dbus-wengao managed startup"
GUI_ROOT="${DBUS_WENGAO_GUI_ROOT:-/var/www/venus/gui-v2}"

RESOLVED_ROOT="$(readlink -f "$APP_ROOT")"
if [[ "$RESOLVED_ROOT" != "$EXPECTED_ROOT" ]]; then
    echo "Refusing to remove unexpected app root: $RESOLVED_ROOT" >&2
    exit 2
fi

"$APP_ROOT/disable.sh"
if [[ -f "$GUI_ROOT/dbus-wengao-gui-v2.json" ]]; then
    if [[ ! -x "$APP_ROOT/gui-v2/restore.sh" ]]; then
        echo "Refusing uninstall: active dbus-wengao GUIv2 has no restore tool" >&2
        exit 2
    fi
    "$APP_ROOT/gui-v2/restore.sh"
fi
if [[ -f "$RC_LOCAL" ]]; then
    sed -i "\\|$BOOT_MARKER|,+1d" "$RC_LOCAL"
fi

echo "Local configuration and GUIv2 backups under /data/setupOptions/WengaoDcdc are preserved."
rm -rf -- "$EXPECTED_ROOT"
