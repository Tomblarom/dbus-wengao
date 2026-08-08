#!/bin/bash
set -euo pipefail

APP_ROOT="${DBUS_WENGAO_ROOT:-/data/apps/dbus-wengao}"
CONFIG_DIR="${DBUS_WENGAO_CONFIG_DIR:-/data/setupOptions/WengaoDcdc}"
CONFIG_FILE="${DBUS_WENGAO_CONFIG:-$CONFIG_DIR/config.toml}"
RC_LOCAL="/data/rc.local"
BOOT_MARKER="# dbus-wengao managed startup"
BOOT_LINE="[ -x $APP_ROOT/enable.sh ] && $APP_ROOT/enable.sh --boot"

mkdir -p "$CONFIG_DIR"
if [[ ! -e "$CONFIG_DIR/config.example.toml" ]]; then
    cp "$APP_ROOT/config/config.example.toml" "$CONFIG_DIR/config.example.toml"
fi

if [[ ! -e "$RC_LOCAL" ]]; then
    printf '%s\n' '#!/bin/bash' > "$RC_LOCAL"
    chmod 755 "$RC_LOCAL"
fi
if ! grep -Fq "$BOOT_MARKER" "$RC_LOCAL"; then
    printf '\n%s\n%s\n' "$BOOT_MARKER" "$BOOT_LINE" >> "$RC_LOCAL"
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "No local configuration found at $CONFIG_FILE"
    echo "A disabled example was copied to $CONFIG_DIR/config.example.toml"
    echo "No dbus-wengao services were enabled."
    exit 0
fi

exec env PYTHONPATH="$APP_ROOT/src" python3 -m wengao.servicegen \
    --app-root "$APP_ROOT" \
    --config "$CONFIG_FILE"

