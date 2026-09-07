#!/bin/bash
set -euo pipefail

GUI_ROOT="${DBUS_WENGAO_GUI_ROOT:-/var/www/venus/gui-v2}"
STATE_ROOT="${DBUS_WENGAO_GUI_STATE_ROOT:-/data/setupOptions/WengaoDcdc/gui-v2}"
LAST_BACKUP="$STATE_ROOT/last-backup"

if [[ ! -f "$GUI_ROOT/dbus-wengao-gui-v2.json" ]]; then
    echo "The active GUIv2 is not marked as a dbus-wengao build" >&2
    exit 2
fi
if [[ ! -f "$LAST_BACKUP" ]]; then
    echo "No dbus-wengao GUIv2 backup is recorded" >&2
    exit 2
fi

BACKUP_NAME="$(cat "$LAST_BACKUP")"
if [[ ! "$BACKUP_NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "Invalid GUIv2 backup name" >&2
    exit 2
fi
BACKUP_ROOT="$STATE_ROOT/backups/$BACKUP_NAME"
if [[ ! -f "$BACKUP_ROOT/venus-gui-v2.wasm.gz" ]]; then
    echo "Recorded GUIv2 backup is incomplete: $BACKUP_ROOT" >&2
    exit 2
fi
if find "$BACKUP_ROOT" -type l -print -quit | grep -q .; then
    echo "Recorded GUIv2 backup must not contain symbolic links" >&2
    exit 2
fi

if [[ "$GUI_ROOT" == "/var/www/venus/gui-v2" && -x /opt/victronenergy/swupdate-scripts/remount-rw.sh ]]; then
    /opt/victronenergy/swupdate-scripts/remount-rw.sh
fi

GUI_PARENT="$(dirname "$GUI_ROOT")"
STAGED_ROOT="$(mktemp -d "$GUI_PARENT/.dbus-wengao-gui-v2.restore.XXXXXX")"
PREVIOUS_ROOT="$GUI_PARENT/.dbus-wengao-gui-v2.modified.$$"
if ! cp -a "$BACKUP_ROOT/." "$STAGED_ROOT/"; then
    rm -rf -- "$STAGED_ROOT"
    exit 1
fi
mv "$GUI_ROOT" "$PREVIOUS_ROOT"
if ! mv "$STAGED_ROOT" "$GUI_ROOT"; then
    if ! mv "$PREVIOUS_ROOT" "$GUI_ROOT"; then
        echo "GUIv2 restore and automatic recovery both failed; recover from $PREVIOUS_ROOT" >&2
    fi
    exit 1
fi
rm -rf -- "$PREVIOUS_ROOT"

if [[ -d /service/vrmlogger ]]; then
    svc -t /service/vrmlogger
fi
echo "Restored original GUIv2 from $BACKUP_ROOT"
