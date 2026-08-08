from __future__ import annotations

import gzip
import hashlib
import os
import stat
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

ROOT = Path(__file__).parents[1]
INSTALLER = ROOT / "gui-v2" / "install.sh"
RESTORER = ROOT / "gui-v2" / "restore.sh"

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the Venus shell scripts require POSIX")


def _write_assets(path: Path) -> None:
    path.mkdir()
    payload = b"patched-wasm"
    (path / "venus-gui-v2.wasm.gz").write_bytes(gzip.compress(payload, mtime=0))
    (path / "venus-gui-v2.wasm.sha256").write_text(
        hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii"
    )
    (path / "venus-gui-v2.wasm.size").write_text(f"{len(payload)}\n", encoding="ascii")
    for name in ("index.html", "qtloader.js", "venus-gui-v2.js", "LICENSE.txt"):
        (path / name).write_text("fixture\n", encoding="utf-8")
    (path / "dbus-wengao-gui-v2.json").write_bytes((ROOT / "gui-v2" / "manifest.json").read_bytes())


def _environment(tmp_path: Path) -> tuple[dict[str, str], Path, Path, Path]:
    executable_root = tmp_path / "bin"
    executable_root.mkdir()
    opkg = executable_root / "opkg"
    opkg.write_text(
        '#!/bin/sh\nprintf "Package: gui-v2-webassembly\\nVersion: 1.3.14-r0\\n"\n',
        encoding="utf-8",
    )
    opkg.chmod(opkg.stat().st_mode | stat.S_IXUSR)

    live_root = tmp_path / "live"
    live_root.mkdir()
    (live_root / "venus-gui-v2.wasm.gz").write_bytes(gzip.compress(b"original-wasm", mtime=0))
    (live_root / "index.html").write_text("original\n", encoding="utf-8")

    state_root = tmp_path / "state"
    assets = tmp_path / "assets"
    _write_assets(assets)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{executable_root}{os.pathsep}{environment['PATH']}",
            "DBUS_WENGAO_GUI_ROOT": str(live_root),
            "DBUS_WENGAO_GUI_STATE_ROOT": str(state_root),
        }
    )
    return environment, live_root, state_root, assets


def _run(
    script: Path, *arguments: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *(str(argument) for argument in arguments)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_install_reinstall_and_restore_preserve_the_original_gui(tmp_path: Path) -> None:
    environment, live_root, state_root, assets = _environment(tmp_path)

    first_install = _run(INSTALLER, assets, environment=environment)
    assert first_install.returncode == 0, first_install.stderr
    backup_name = (state_root / "last-backup").read_text(encoding="ascii").strip()
    backup_root = state_root / "backups" / backup_name
    assert gzip.decompress((backup_root / "venus-gui-v2.wasm.gz").read_bytes()) == b"original-wasm"

    reinstall = _run(INSTALLER, assets, environment=environment)
    assert reinstall.returncode == 0, reinstall.stderr
    assert (state_root / "last-backup").read_text(encoding="ascii").strip() == backup_name
    assert [path.name for path in (state_root / "backups").iterdir()] == [backup_name]

    restore = _run(RESTORER, environment=environment)
    assert restore.returncode == 0, restore.stderr
    assert not (live_root / "dbus-wengao-gui-v2.json").exists()
    assert gzip.decompress((live_root / "venus-gui-v2.wasm.gz").read_bytes()) == b"original-wasm"


def test_install_accepts_valid_archive_and_rejects_path_traversal(tmp_path: Path) -> None:
    environment, live_root, _, assets = _environment(tmp_path)
    archive = tmp_path / "gui.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as target:
        for source in sorted(assets.iterdir()):
            target.write(source, f"wasm/{source.name}")

    valid_install = _run(INSTALLER, archive, environment=environment)
    assert valid_install.returncode == 0, valid_install.stderr
    assert (live_root / "dbus-wengao-gui-v2.json").is_file()

    malicious_archive = tmp_path / "malicious.zip"
    with ZipFile(malicious_archive, "w") as target:
        target.writestr("../escaped", "bad")
    rejected_install = _run(INSTALLER, malicious_archive, environment=environment)
    assert rejected_install.returncode != 0
    assert "unsafe archive member" in rejected_install.stderr
    assert not (tmp_path / "escaped").exists()
