#!/bin/bash
set -euo pipefail

APP_ROOT="${DBUS_WENGAO_ROOT:-/data/apps/dbus-wengao}"
SERVICE_SOURCE="$APP_ROOT/contrib/venus-time-sync/service"
SERVICE_LINK="/service/venus-time-sync"
RC_LOCAL="/data/rc.local"
BOOT_MARKER="# venus-time-sync managed startup"
BOOT_LINE="[ -x $APP_ROOT/contrib/venus-time-sync/enable.sh ] && $APP_ROOT/contrib/venus-time-sync/enable.sh --boot"

if [[ ! -x "$SERVICE_SOURCE/run" || ! -f "$APP_ROOT/contrib/venus-time-sync/time_sync.py" ]]; then
    echo "venus-time-sync files are incomplete under $APP_ROOT" >&2
    exit 2
fi

mkdir -p /data/var/lib/venus-time-sync /var/log/venus-time-sync

if [[ -e "$SERVICE_LINK" && ! -L "$SERVICE_LINK" ]]; then
    echo "$SERVICE_LINK exists and is not a symbolic link" >&2
    exit 2
fi
ln -sfn "$SERVICE_SOURCE" "$SERVICE_LINK"

if [[ "${1:-}" != "--boot" ]]; then
    if [[ ! -e "$RC_LOCAL" ]]; then
        printf '%s\n' '#!/bin/bash' > "$RC_LOCAL"
        chmod 755 "$RC_LOCAL"
    fi
    if ! grep -Fq "$BOOT_MARKER" "$RC_LOCAL"; then
        printf '\n%s\n%s\n' "$BOOT_MARKER" "$BOOT_LINE" >> "$RC_LOCAL"
    fi
fi

for _ in {1..30}; do
    if svok "$SERVICE_LINK" 2>/dev/null && svok "$SERVICE_LINK/log" 2>/dev/null; then
        svc -u "$SERVICE_LINK/log"
        svc -u "$SERVICE_LINK"
        echo "venus-time-sync enabled"
        exit 0
    fi
    sleep 1
done

echo "runsv did not discover $SERVICE_LINK" >&2
exit 1
