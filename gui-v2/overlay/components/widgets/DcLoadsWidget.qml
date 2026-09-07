/*
** Copyright (C) 2023 Victron Energy B.V.
** See LICENSE.txt for license information.
**
** This code is based on Victron Energy code.
** Modified by the dbus-wengao contributors to show per-device DC load power.
*/

import QtQuick
import QtQuick.Layouts
import Victron.VenusOS

OverviewWidget {
	id: root

	function includeLoadDevice(_device, childItems) {
		const policy = childItems["WengaoShowUnavailable"]
		if (!policy || policy.value === undefined) {
			return true
		}
		const connected = childItems["Connected"]
		return policy.value === 1 || connected?.value === 1
	}

	//% "DC Loads"
	title: qsTrId("overview_widget_dcloads_title")
	type: VenusOS.OverviewWidget_Type_DcLoads
	enabled: systemLoadDevices.count > 1 || nonSystemLoadDevices.count > 0
	preferredSize: loadDevices.count > 1 ? VenusOS.OverviewWidget_PreferredSize_PreferLarge : VenusOS.OverviewWidget_PreferredSize_Any

	contentItem: ColumnLayout {
		spacing: Theme.geometry_overviewPage_widget_content_spacing

		WidgetHeader {
			text: root.title
			icon.source: "qrc:/images/dcloads.svg"
			Layout.fillWidth: true
		}

		OverviewElectricalQuantityLabel {
			widgetSize: root.size
			dataObject: Global.system.dc
			sourceType: VenusOS.ElectricalQuantity_Source_Dc
			Layout.fillWidth: true
			Layout.fillHeight: true
		}

		ColumnLayout {
			spacing: 0
			Layout.fillWidth: true
			Layout.alignment: Qt.AlignBottom

			Repeater {
				model: loadDevices

				delegate: Item {
					id: deviceDelegate

					required property Device device
					readonly property bool displayOfflineAsZero: showUnavailableItem.valid
							&& showUnavailableItem.value === 1
							&& connectedItem.value !== 1

					Layout.fillWidth: true
					implicitHeight: Math.max(deviceLabel.implicitHeight, powerLabel.implicitHeight)

					Label {
						id: deviceLabel

						anchors {
							left: parent.left
							right: powerLabel.left
							verticalCenter: parent.verticalCenter
						}
						text: device.name + ":"
						elide: Text.ElideRight
						font.pixelSize: root.tertiaryFontSize
						color: powerLabel.unitColor
					}

					ElectricalQuantityLabel {
						id: powerLabel

						anchors {
							right: parent.right
							verticalCenter: parent.verticalCenter
						}
						dataObject: QtObject {
							readonly property real power: deviceDelegate.displayOfflineAsZero
									? 0
									: dcLoadDevice.power
							readonly property real current: NaN
						}
						sourceType: VenusOS.ElectricalQuantity_Source_Any
						alignment: Qt.AlignRight
						font.pixelSize: root.tertiaryFontSize
						valueColor: Theme.color_font_primary
						unitColor: Theme.color_font_secondary
					}

					DcDevice {
						id: dcLoadDevice
						serviceUid: device.serviceUid
					}

					VeQuickItem {
						id: connectedItem
						uid: device.serviceUid + "/Connected"
					}

					VeQuickItem {
						id: showUnavailableItem
						uid: device.serviceUid + "/WengaoShowUnavailable"
					}
				}
			}
		}
	}

	onClicked: {
		Global.pageManager.pushPage("/pages/loads/DcLoadListPage.qml", {
			title: root.title,
			systemModel: systemLoadDevices,
			nonSystemModel: nonSystemLoadDevices
		});
	}

	FilteredDeviceModel {
		id: loadDevices
		serviceTypes: ["dcsystem", "dcload", "dcdc", "motordrive"]
		childFilterIds: {
			"dcsystem": ["Connected", "WengaoShowUnavailable"],
			"dcload": ["Connected", "WengaoShowUnavailable"],
			"dcdc": ["Connected", "WengaoShowUnavailable"],
			"motordrive": ["Connected", "WengaoShowUnavailable"]
		}
		childFilterFunction: root.includeLoadDevice
	}

	FilteredDeviceModel {
		id: systemLoadDevices
		serviceTypes: ["dcsystem"]
		childFilterIds: { "dcsystem": ["Connected", "WengaoShowUnavailable"] }
		childFilterFunction: root.includeLoadDevice
	}

	FilteredDeviceModel {
		id: nonSystemLoadDevices
		serviceTypes: ["dcload", "dcdc", "motordrive"]
		childFilterIds: {
			"dcload": ["Connected", "WengaoShowUnavailable"],
			"dcdc": ["Connected", "WengaoShowUnavailable"],
			"motordrive": ["Connected", "WengaoShowUnavailable"]
		}
		childFilterFunction: root.includeLoadDevice
	}
}
