#!/usr/bin/env python3
"""Stamp generated GUIv2 asset requests with the dbus-wengao overlay revision."""

from __future__ import annotations

import re
import sys
from pathlib import Path

SAFE_REVISION = re.compile(r"^[A-Za-z0-9._-]+$")


def apply_cache_buster(index_path: Path, revision: str) -> None:
    if not SAFE_REVISION.fullmatch(revision):
        raise ValueError(f"unsafe GUI revision: {revision!r}")

    content = index_path.read_text(encoding="utf-8")
    replacements = {
        "fetch('venus-gui-v2.wasm.size')": f"fetch('venus-gui-v2.wasm.size?v={revision}')",
        "fetch('venus-gui-v2.wasm.sha256')": (
            f"fetch('venus-gui-v2.wasm.sha256?v={revision}')"
        ),
        "preloadWasm('venus-gui-v2.wasm'": (
            f"preloadWasm('venus-gui-v2.wasm?v={revision}'"
        ),
        'src="venus-gui-v2.js"': f'src="venus-gui-v2.js?v={revision}"',
        'src="qtloader.js"': f'src="qtloader.js?v={revision}"',
    }
    for original, stamped in replacements.items():
        count = content.count(original)
        if count != 1:
            raise ValueError(
                f"expected exactly one {original!r} in {index_path}, found {count}"
            )
        content = content.replace(original, stamped)

    marker = f'<meta name="dbus-wengao-gui-revision" content="{revision}">'
    if content.count("</head>") != 1:
        raise ValueError(f"expected exactly one closing head tag in {index_path}")
    content = content.replace("</head>", f"    {marker}\n  </head>")
    index_path.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {Path(sys.argv[0]).name} <index.html> <revision>", file=sys.stderr)
        return 2
    try:
        apply_cache_buster(Path(sys.argv[1]), sys.argv[2])
    except (OSError, ValueError) as error:
        print(f"Unable to stamp GUIv2 asset URLs: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
