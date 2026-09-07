#!/bin/bash
set -euo pipefail

APP_ROOT="${DBUS_WENGAO_ROOT:-/data/apps/dbus-wengao}"
EXPECTED_ROOT="/data/apps/dbus-wengao"
RC_LOCAL="/data/rc.local"
BOOT_MARKER="# dbus-wengao managed startup"

RESOLVED_ROOT="$(readlink -f "$APP_ROOT")"
if [[ "$RESOLVED_ROOT" != "$EXPECTED_ROOT" ]]; then
    echo "Refusing to remove unexpected app root: $RESOLVED_ROOT" >&2
    exit 2
fi

"$APP_ROOT/disable.sh"
if [[ -f "$RC_LOCAL" ]]; then
    sed -i "\\|$BOOT_MARKER|,+1d" "$RC_LOCAL"
fi

echo "Local configuration under /data/setupOptions/WengaoDcdc is preserved."
rm -rf -- "$EXPECTED_ROOT"
