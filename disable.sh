#!/bin/bash
set -euo pipefail

APP_ROOT="${DBUS_WENGAO_ROOT:-/data/apps/dbus-wengao}"

exec env PYTHONPATH="$APP_ROOT/src" python3 -m wengao.servicegen \
    --app-root "$APP_ROOT" \
    --disable

