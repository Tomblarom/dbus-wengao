#!/bin/bash
set -euo pipefail

APP_ROOT="${DBUS_WENGAO_ROOT:-/data/apps/dbus-wengao}"

"$APP_ROOT/enable.sh"
for service in /service/dbus-wengao.*; do
    [[ -L "$service" ]] || continue
    svc -t "$service"
done

