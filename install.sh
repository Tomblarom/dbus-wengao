#!/bin/bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Usage: $0 vX.Y.Z" >&2
    exit 2
fi

TAG="$1"
APP_ROOT="/data/apps/dbus-wengao"
APPS_ROOT="/data/apps"
ARCHIVE="dbus-wengao-$TAG.tar.gz"
BASE_URL="https://github.com/Tomblarom/dbus-wengao/releases/download/$TAG"
TEMP_ROOT="$(mktemp -d /tmp/dbus-wengao-install.XXXXXX)"
BACKUP_ROOT="$APPS_ROOT/.dbus-wengao.previous"
trap 'rm -rf -- "$TEMP_ROOT"' EXIT

curl -fL "$BASE_URL/$ARCHIVE" -o "$TEMP_ROOT/$ARCHIVE"
curl -fL "$BASE_URL/$ARCHIVE.sha256" -o "$TEMP_ROOT/$ARCHIVE.sha256"
(
    cd "$TEMP_ROOT"
    sha256sum -c "$ARCHIVE.sha256"
    tar -xzf "$ARCHIVE"
)

STAGED_ROOT="$TEMP_ROOT/dbus-wengao-$TAG"
if [[ ! -x "$STAGED_ROOT/enable.sh" || ! -f "$STAGED_ROOT/version" ]]; then
    echo "Release archive has an invalid package layout" >&2
    exit 2
fi

if [[ -x "$APP_ROOT/disable.sh" ]]; then
    "$APP_ROOT/disable.sh"
fi
if [[ -e "$BACKUP_ROOT" ]]; then
    rm -rf -- "$BACKUP_ROOT"
fi
if [[ -d "$APP_ROOT" ]]; then
    mv "$APP_ROOT" "$BACKUP_ROOT"
fi

if ! mv "$STAGED_ROOT" "$APP_ROOT"; then
    [[ ! -d "$APP_ROOT" && -d "$BACKUP_ROOT" ]] && mv "$BACKUP_ROOT" "$APP_ROOT"
    exit 1
fi

if ! "$APP_ROOT/enable.sh"; then
    rm -rf -- "$APP_ROOT"
    [[ -d "$BACKUP_ROOT" ]] && mv "$BACKUP_ROOT" "$APP_ROOT"
    exit 1
fi
rm -rf -- "$BACKUP_ROOT"
echo "Installed dbus-wengao $TAG"

