#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="$SCRIPT_DIR/manifest.json"
GUI_ROOT="${DBUS_WENGAO_GUI_ROOT:-/var/www/venus/gui-v2}"
STATE_ROOT="${DBUS_WENGAO_GUI_STATE_ROOT:-/data/setupOptions/WengaoDcdc/gui-v2}"

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <wasm-directory|venus-webassembly.zip>" >&2
    exit 2
fi

manifest_value() {
    python3 - "$MANIFEST" "$1" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)[sys.argv[2]])
PY
}

EXPECTED_PACKAGE="$(manifest_value venus_package)"
EXPECTED_VERSION="$(manifest_value venus_package_version)"
INSTALLED_VERSION="$(opkg status "$EXPECTED_PACKAGE" 2>/dev/null | awk '$1 == "Version:" {print $2; exit}')"
if [[ "$INSTALLED_VERSION" != "$EXPECTED_VERSION" ]]; then
    echo "Refusing GUIv2 install: expected $EXPECTED_PACKAGE $EXPECTED_VERSION, found ${INSTALLED_VERSION:-none}" >&2
    exit 2
fi

TEMP_ROOT=""
cleanup() {
    if [[ -n "$TEMP_ROOT" ]]; then
        case "$TEMP_ROOT" in
            /tmp/dbus-wengao-gui-v2-install.*) rm -rf -- "$TEMP_ROOT" ;;
            *) echo "Refusing to remove unexpected temporary path: $TEMP_ROOT" >&2 ;;
        esac
    fi
}
trap cleanup EXIT

if [[ -d "$1" ]]; then
    ASSET_ROOT="$(readlink -f "$1")"
elif [[ -f "$1" ]]; then
    TEMP_ROOT="$(mktemp -d /tmp/dbus-wengao-gui-v2-install.XXXXXX)"
    python3 - "$1" "$TEMP_ROOT" <<'PY'
from pathlib import Path, PurePosixPath
import stat
import sys
from zipfile import BadZipFile, ZipFile

archive = Path(sys.argv[1])
destination = Path(sys.argv[2])
maximum_file_size = 512 * 1024 * 1024
maximum_total_size = 1024 * 1024 * 1024
total_size = 0

try:
    with ZipFile(archive) as source:
        seen = set()
        for member in source.infolist():
            name = member.filename
            path = PurePosixPath(name)
            mode = member.external_attr >> 16
            if (
                not name
                or "\\" in name
                or path.is_absolute()
                or not path.parts
                or path.parts[0] != "wasm"
                or ".." in path.parts
                or name in seen
                or stat.S_ISLNK(mode)
            ):
                raise ValueError(f"unsafe archive member: {name!r}")
            if member.file_size > maximum_file_size:
                raise ValueError(f"archive member is too large: {name!r}")
            total_size += member.file_size
            if total_size > maximum_total_size:
                raise ValueError("archive is too large")
            seen.add(name)
        source.extractall(destination)
except (BadZipFile, OSError, ValueError) as error:
    raise SystemExit(f"Invalid GUIv2 archive: {error}")
PY
    ASSET_ROOT="$TEMP_ROOT/wasm"
else
    echo "GUIv2 asset does not exist: $1" >&2
    exit 2
fi

for required in index.html qtloader.js venus-gui-v2.js venus-gui-v2.wasm.gz \
        venus-gui-v2.wasm.sha256 venus-gui-v2.wasm.size LICENSE.txt \
        dbus-wengao-gui-v2.json; do
    if [[ ! -f "$ASSET_ROOT/$required" ]]; then
        echo "GUIv2 asset is missing $required" >&2
        exit 2
    fi
done
if find "$ASSET_ROOT" -type l -print -quit | grep -q .; then
    echo "GUIv2 asset must not contain symbolic links" >&2
    exit 2
fi
if ! cmp -s "$MANIFEST" "$ASSET_ROOT/dbus-wengao-gui-v2.json"; then
    echo "GUIv2 asset manifest does not match this driver version" >&2
    exit 2
fi

EXPECTED_WASM_HASH="$(awk 'NF {print $1; exit}' "$ASSET_ROOT/venus-gui-v2.wasm.sha256")"
ACTUAL_WASM_HASH="$(gzip -dc "$ASSET_ROOT/venus-gui-v2.wasm.gz" | sha256sum | awk '{print $1}')"
if [[ ! "$EXPECTED_WASM_HASH" =~ ^[0-9a-f]{64}$ || "$ACTUAL_WASM_HASH" != "$EXPECTED_WASM_HASH" ]]; then
    echo "GUIv2 WASM checksum verification failed" >&2
    exit 2
fi

if [[ "$GUI_ROOT" == "/var/www/venus/gui-v2" && -x /opt/victronenergy/swupdate-scripts/remount-rw.sh ]]; then
    /opt/victronenergy/swupdate-scripts/remount-rw.sh
fi
if [[ ! -d "$GUI_ROOT" ]]; then
    echo "GUIv2 target does not exist: $GUI_ROOT" >&2
    exit 2
fi

mkdir -p "$STATE_ROOT/backups"
if [[ -f "$GUI_ROOT/dbus-wengao-gui-v2.json" ]]; then
    if [[ ! -f "$STATE_ROOT/last-backup" ]]; then
        echo "Refusing reinstall: the modified GUIv2 has no recorded original backup" >&2
        exit 2
    fi
    BACKUP_NAME="$(cat "$STATE_ROOT/last-backup")"
    if [[ ! "$BACKUP_NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
        echo "Refusing reinstall: invalid original backup name" >&2
        exit 2
    fi
    BACKUP_ROOT="$STATE_ROOT/backups/$BACKUP_NAME"
    if [[ ! -f "$BACKUP_ROOT/venus-gui-v2.wasm.gz" ]]; then
        echo "Refusing reinstall: the recorded original backup is incomplete" >&2
        exit 2
    fi
else
    CURRENT_HASH="$(gzip -dc "$GUI_ROOT/venus-gui-v2.wasm.gz" | sha256sum | awk '{print $1}')"
    BACKUP_NAME="$EXPECTED_VERSION-$CURRENT_HASH"
    BACKUP_ROOT="$STATE_ROOT/backups/$BACKUP_NAME"
    if [[ ! -d "$BACKUP_ROOT" ]]; then
        mkdir -p "$BACKUP_ROOT"
        cp -a "$GUI_ROOT/." "$BACKUP_ROOT/"
    fi
    printf '%s\n' "$BACKUP_NAME" > "$STATE_ROOT/last-backup"
fi

GUI_PARENT="$(dirname "$GUI_ROOT")"
STAGED_ROOT="$(mktemp -d "$GUI_PARENT/.dbus-wengao-gui-v2.new.XXXXXX")"
PREVIOUS_ROOT="$GUI_PARENT/.dbus-wengao-gui-v2.previous.$$"
if ! cp -a "$ASSET_ROOT/." "$STAGED_ROOT/"; then
    rm -rf -- "$STAGED_ROOT"
    exit 1
fi
mv "$GUI_ROOT" "$PREVIOUS_ROOT"
if ! mv "$STAGED_ROOT" "$GUI_ROOT"; then
    if ! mv "$PREVIOUS_ROOT" "$GUI_ROOT"; then
        echo "GUIv2 replacement and automatic recovery both failed; recover from $PREVIOUS_ROOT" >&2
    fi
    exit 1
fi
rm -rf -- "$PREVIOUS_ROOT"

if [[ -d /service/vrmlogger ]]; then
    svc -t /service/vrmlogger
fi
echo "Installed dbus-wengao GUIv2 load breakdown for $EXPECTED_VERSION"
echo "Original GUIv2 backup: $BACKUP_ROOT"
