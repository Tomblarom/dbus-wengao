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
        "patch_id": "overview-breakdowns-v3",
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
    assert 'serviceTypes: ["alternator", "dcsystem", "dcload", "dcdc", "motordrive"]' in widget
    assert re.search(r"Repeater\s*\{\s*model:\s*loadDevices", widget)
    assert "OverviewWidget_PreferredSize_PreferLarge" in widget
    assert "widgetSize: root.size" in widget
    assert "Layout.fillHeight: true" in widget
    assert widget.count("font.pixelSize: root.tertiaryFontSize") == 2
    assert "customNameItem.value || productNameItem.value" in widget
    assert "valueColor: Theme.color_font_primary" in widget
    assert "unitColor: Theme.color_font_secondary" in widget
    assert "displayOfflineAsZero" in widget
    assert 'uid: deviceDelegate.serviceUid + "/Wengao/DcLoadPower"' in widget
    assert "!dcLoadPowerItem.valid" in widget
    assert 'uid: deviceDelegate.serviceUid + "/WengaoShowUnavailable"' in widget
    assert '"dcsystem": ["Connected", "WengaoShowUnavailable"]' in widget
    assert "sourceType: VenusOS.ElectricalQuantity_Source_Any" in widget
    assert 'childId: "WengaoDisplayOrder"' in widget
    assert "sortColumn: orderedChildren.sortValueColumn" in widget


def test_gui_overlay_contains_no_installation_specific_identity() -> None:
    for path in (GUI_ROOT / "overlay").rglob("*.qml"):
        content = path.read_text(encoding="utf-8")
        assert not re.search(r"wengao[_-]\d|/dev/|192\.168\.", content, re.IGNORECASE)


def test_dc_load_detail_page_uses_the_same_offline_zero_policy() -> None:
    page = (GUI_ROOT / "overlay" / "pages" / "loads" / "DcLoadListPage.qml").read_text(
        encoding="utf-8"
    )
    assert "This code is based on Victron Energy code" in page
    assert page.count("displayOfflineAsZero") >= 4
    assert page.count('WengaoShowUnavailable"') == 2
    assert "power: displayOfflineAsZero ? 0" in page


def test_battery_widget_patch_lists_wengao_secondary_batteries() -> None:
    patch = (GUI_ROOT / "patches" / "battery-widget-secondary-batteries.patch").read_text(
        encoding="utf-8"
    )
    assert "_secondaryBatteries" in patch
    assert "!battery.active_battery_service" in patch
    assert 'battery.id.startsWith("com.victronenergy.battery.wengao_")' in patch
    assert "modelData.name" in patch
    assert "modelData.voltage ?? NaN" in patch
    assert "Theme.font_overviewPage_battery_small" in patch


def test_gui_build_installs_all_overlays() -> None:
    build_script = (GUI_ROOT / "build-wasm.sh").read_text(encoding="utf-8")
    assert '"$WIDGET_OVERLAY" "$SOURCE_ROOT/components/widgets/DcLoadsWidget.qml"' in build_script
    assert '"$LIST_PAGE_OVERLAY" "$SOURCE_ROOT/pages/loads/DcLoadListPage.qml"' in build_script
    assert 'patch --batch --directory="$SOURCE_ROOT" --strip=1' in build_script
    assert '"$BATTERY_WIDGET_PATCH"' in build_script


def test_uninstall_restores_an_active_gui_before_removing_the_app() -> None:
    uninstall = (ROOT / "uninstall.sh").read_text(encoding="utf-8")
    assert uninstall.index('"$APP_ROOT/gui-v2/restore.sh"') < uninstall.index(
        'rm -rf -- "$EXPECTED_ROOT"'
    )
