#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$SCRIPT_DIR/manifest.json"
WIDGET_OVERLAY="$SCRIPT_DIR/overlay/components/widgets/DcLoadsWidget.qml"
LIST_PAGE_OVERLAY="$SCRIPT_DIR/overlay/pages/loads/DcLoadListPage.qml"
OUTPUT_ROOT="$REPO_ROOT/dist/gui-v2"

manifest_value() {
    python3 - "$MANIFEST" "$1" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)[sys.argv[2]])
PY
}

UPSTREAM_REPOSITORY="$(manifest_value upstream_repository)"
UPSTREAM_TAG="$(manifest_value upstream_tag)"
UPSTREAM_COMMIT="$(manifest_value upstream_commit)"

if [[ ! "$UPSTREAM_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Invalid pinned GUIv2 commit: $UPSTREAM_COMMIT" >&2
    exit 2
fi

BUILD_ROOT="$(mktemp -d /tmp/dbus-wengao-gui-v2-build.XXXXXX)"
cleanup() {
    case "$BUILD_ROOT" in
        /tmp/dbus-wengao-gui-v2-build.*) rm -rf -- "$BUILD_ROOT" ;;
        *) echo "Refusing to remove unexpected build path: $BUILD_ROOT" >&2 ;;
    esac
}
trap cleanup EXIT

SOURCE_ROOT="$BUILD_ROOT/gui-v2"
git clone --depth 1 --branch "$UPSTREAM_TAG" --recurse-submodules \
    "$UPSTREAM_REPOSITORY" "$SOURCE_ROOT"

ACTUAL_COMMIT="$(git -C "$SOURCE_ROOT" rev-parse HEAD)"
if [[ "$ACTUAL_COMMIT" != "$UPSTREAM_COMMIT" ]]; then
    echo "GUIv2 tag moved: expected $UPSTREAM_COMMIT, got $ACTUAL_COMMIT" >&2
    exit 2
fi

install -m 0644 "$WIDGET_OVERLAY" "$SOURCE_ROOT/components/widgets/DcLoadsWidget.qml"
install -m 0644 "$LIST_PAGE_OVERLAY" "$SOURCE_ROOT/pages/loads/DcLoadListPage.qml"
(
    cd "$SOURCE_ROOT"
    bash scripts/build-wasm.sh
)

if [[ "$OUTPUT_ROOT" != "$REPO_ROOT/dist/gui-v2" ]]; then
    echo "Refusing to replace unexpected output path: $OUTPUT_ROOT" >&2
    exit 2
fi
rm -rf -- "$OUTPUT_ROOT"
mkdir -p "$OUTPUT_ROOT"
cp -a "$SOURCE_ROOT/build-wasm_files_to_copy/wasm" "$OUTPUT_ROOT/wasm"
install -m 0644 "$MANIFEST" "$OUTPUT_ROOT/wasm/dbus-wengao-gui-v2.json"
python3 - "$OUTPUT_ROOT" <<'PY'
from pathlib import Path
import stat
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

output_root = Path(sys.argv[1])
archive = output_root / "venus-webassembly.zip"
with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as target:
    for source in sorted((output_root / "wasm").rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(output_root).as_posix()
        info = ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = ZIP_DEFLATED
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        target.writestr(info, source.read_bytes(), compresslevel=9)
PY
(
    cd "$OUTPUT_ROOT"
    sha256sum venus-webassembly.zip > venus-webassembly.zip.sha256
)

echo "Built $OUTPUT_ROOT/venus-webassembly.zip"
