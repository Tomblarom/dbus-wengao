from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
GUI_ROOT = ROOT / "gui-v2"


def test_gui_manifest_pins_the_validated_venus_version() -> None:
    manifest = json.loads((GUI_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == {
        "schema_version": 1,
        "patch_id": "dc-load-breakdown-v1",
        "upstream_repository": "https://github.com/victronenergy/gui-v2.git",
        "upstream_tag": "v1.3.14",
        "upstream_commit": "c8f5a14353d1c6dc7554cbc8bf5d167af8fd00d7",
        "upstream_license": "Victron Energy OS license v1",
        "venus_package": "gui-v2-webassembly",
        "venus_package_version": "1.3.14-r0",
    }


def test_dc_load_widget_lists_each_device_and_its_power() -> None:
    widget = (GUI_ROOT / "overlay" / "components" / "widgets" / "DcLoadsWidget.qml").read_text(
        encoding="utf-8"
    )
    assert "This code is based on Victron Energy code" in widget
    assert re.search(r"id:\s*loadDevices", widget)
    assert 'serviceTypes: ["dcsystem", "dcload", "dcdc", "motordrive"]' in widget
    assert re.search(r"Repeater\s*\{\s*model:\s*loadDevices", widget)
    assert "OverviewWidget_PreferredSize_PreferLarge" in widget
    assert widget.count("Theme.font_overviewPage_widget_phase_minimumSize") == 2
    assert "text: device.name" in widget
    assert "dataObject: dcLoadDevice" in widget
    assert "serviceUid: device.serviceUid" in widget


def test_gui_overlay_contains_no_installation_specific_identity() -> None:
    widget = (GUI_ROOT / "overlay" / "components" / "widgets" / "DcLoadsWidget.qml").read_text(
        encoding="utf-8"
    )
    assert not re.search(r"wengao[_-]\d|/dev/|192\.168\.", widget, re.IGNORECASE)


def test_uninstall_restores_an_active_gui_before_removing_the_app() -> None:
    uninstall = (ROOT / "uninstall.sh").read_text(encoding="utf-8")
    assert uninstall.index('"$APP_ROOT/gui-v2/restore.sh"') < uninstall.index(
        'rm -rf -- "$EXPECTED_ROOT"'
    )
