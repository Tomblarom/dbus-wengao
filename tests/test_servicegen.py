from __future__ import annotations

from pathlib import Path

import pytest

from wengao.errors import ConfigurationError
from wengao.servicegen import disable_services, generate_services


def write_test_app(tmp_path: Path, *, enabled: bool = True) -> tuple[Path, Path]:
    app_root = tmp_path / "app"
    template = app_root / "service"
    (template / "log").mkdir(parents=True)
    (template / "run").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (template / "log" / "run").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""config_version = 1
[[devices]]
id = "test-device"
enabled = {str(enabled).lower()}
profile = "bidirectional-battery-link"
port = "/dev/serial/by-path/synthetic"
slave_address = 1
system_terminal = "B"
device_instance = 40
custom_name = "Test device"
venus_role = "dcsystem"
control_mode = "monitor-only"
dvcc_policy = "disabled"
allowed_directions = ["A-to-B", "B-to-A"]
locked_direction = ""
[devices.permissions]
""",
        encoding="utf-8",
    )
    return app_root, config_path


def test_generate_creates_one_isolated_service_per_enabled_device(tmp_path: Path) -> None:
    app_root, config_path = write_test_app(tmp_path)
    names = generate_services(app_root=app_root, config_path=config_path, link_root=None)
    assert names == ("dbus-wengao.test-device",)
    service = app_root / "generated-services" / names[0]
    assert (service / "run").is_file()
    assert (service / "log" / "run").is_file()


def test_disabled_device_creates_no_service(tmp_path: Path) -> None:
    app_root, config_path = write_test_app(tmp_path, enabled=False)
    assert generate_services(app_root=app_root, config_path=config_path, link_root=None) == ()


def test_missing_templates_fail_without_partial_service(tmp_path: Path) -> None:
    app_root, config_path = write_test_app(tmp_path)
    (app_root / "service" / "run").unlink()
    with pytest.raises(ConfigurationError, match="templates are missing"):
        generate_services(app_root=app_root, config_path=config_path, link_root=None)


def test_generator_refuses_to_replace_non_symlink_service(tmp_path: Path) -> None:
    app_root, config_path = write_test_app(tmp_path)
    link_root = tmp_path / "service-links"
    link_root.mkdir()
    conflicting = link_root / "dbus-wengao.test-device"
    conflicting.mkdir()
    with pytest.raises(ConfigurationError, match="non-symlink"):
        generate_services(app_root=app_root, config_path=config_path, link_root=link_root)


def test_disable_ignores_non_symlinks_and_foreign_links(tmp_path: Path) -> None:
    app_root, _config_path = write_test_app(tmp_path)
    link_root = tmp_path / "service-links"
    link_root.mkdir()
    (link_root / "dbus-wengao.foreign").write_text("not a link", encoding="utf-8")
    assert disable_services(app_root=app_root, link_root=link_root) == ()
    assert (link_root / "dbus-wengao.foreign").exists()
