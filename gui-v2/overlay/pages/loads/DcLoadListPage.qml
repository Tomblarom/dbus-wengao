/*
** Copyright (C) 2025 Victron Energy B.V.
** See LICENSE.txt for license information.
**
** This code is based on Victron Energy code.
** Modified by the dbus-wengao contributors to display configured offline loads as zero.
*/

import QtQuick
import Victron.VenusOS

Page {
	id: root

	required property FilteredDeviceModel systemModel
	required property FilteredDeviceModel nonSystemModel

	function _showSettingsPage(device) {
		if (BackendConnection.serviceTypeFromUid(device.serviceUid) === "dcdc") {
			Global.pageManager.pushPage("/pages/settings/devicelist/dc-in/PageDcDcConverter.qml",
					{ "bindPrefix": device.serviceUid })
		} else {
			Global.pageManager.pushPage("/pages/settings/devicelist/dc-in/PageDcMeter.qml",
					{ "bindPrefix": device.serviceUid })
		}
	}

	Component {
		id: headerComponent

		ListItem {
			id: tableListItem

			topPadding: 0
			bottomPadding: bottomInset
			leftPadding: leftInset
			rightPadding: rightInset

			contentItem: HorizontalFlickable {
				readonly property real columnWidth: loadSummary.fixedColumnWidth
				readonly property real columnSpacing: loadSummary.columnSpacing

				implicitHeight: dcsystemTable.y + dcsystemTable.height
				contentWidth: Math.max(Theme.geometry_quantityTable_maximumWidth_small, tableListItem.availableWidth)

				QuantityTableSummary {
					id: loadSummary

					width: parent.width
					equalWidthColumns: true
					rightPadding: Theme.geometry_icon_size_medium + tableListItem.horizontalContentPadding
					summaryModel: [
						{ text: "", unit: VenusOS.Units_None },
						{ text: "", unit: VenusOS.Units_None },
						{ text: CommonWords.power_watts, unit: VenusOS.Units_None },
					]
					bodyHeaderText: CommonWords.total
					bodyModel: QuantityObjectModel {
						QuantityObject { unit: VenusOS.Units_Volt_DC; hidden: true }
						QuantityObject { unit: VenusOS.Units_Amp; hidden: true }
						QuantityObject { object: Global.system.dc; key: "power"; unit: VenusOS.Units_Watt }
					}
				}

				QuantityTable {
					id: dcsystemTable

					anchors.top: loadSummary.bottom
					width: parent.width
					rightPadding: loadSummary.rightPadding
					equalWidthColumns: true
					model: root.systemModel.count > 1 ? root.systemModel : null
					delegate: QuantityTable.TableRow {
						id: dcsystemTableRow

						required property Device device
						readonly property bool displayOfflineAsZero: showUnavailableItem.valid
								&& showUnavailableItem.value === 1
								&& connectedItem.value !== 1

						headerText: dcSystemDevice.name
						model: QuantityObjectModel {
							QuantityObject { object: displayDevice; key: "voltage"; unit: VenusOS.Units_Volt_DC }
							QuantityObject { object: displayDevice; key: "current"; unit: VenusOS.Units_Amp }
							QuantityObject { object: displayDevice; key: "power"; unit: VenusOS.Units_Watt }
						}

						QtObject {
							id: displayDevice
							readonly property real voltage: dcSystemDevice.voltage
							readonly property real current: dcSystemDevice.current
							readonly property real power: dcsystemTableRow.displayOfflineAsZero
									? 0
									: dcSystemDevice.power
						}

						DcDevice {
							id: dcSystemDevice
							serviceUid: dcsystemTableRow.device.serviceUid
						}

						VeQuickItem {
							id: connectedItem
							uid: dcsystemTableRow.device.serviceUid + "/Connected"
						}

						VeQuickItem {
							id: showUnavailableItem
							uid: dcsystemTableRow.device.serviceUid + "/WengaoShowUnavailable"
						}
					}
				}
			}
		}
	}

	GradientListView {
		header: root.systemModel.count > 1 ? headerComponent: null
		model: root.nonSystemModel
		delegate: LoadListDelegate {
			id: deviceDelegate

			required property var device
			readonly property bool displayOfflineAsZero: showUnavailableItem.valid
					&& showUnavailableItem.value === 1
					&& connectedItem.value !== 1

			name: device.name
			power: displayOfflineAsZero ? 0 : (dcDevice.power ?? NaN)
			current: dcDevice.current ?? NaN
			temperature: temperatureItem.value ?? NaN
			columnWidth: ListView.view.headerItem?.contentItem?.columnWidth ?? Theme.geometry_loadListPage_defaultColumnWidth
			columnSpacing: ListView.view.headerItem?.contentItem?.columnSpacing ?? Theme.geometry_quantityTable_horizontalSpacing_large
			unitAmps: root.systemModel.count <= 1 && !isNaN(current)
				&& (Global.systemSettings.electricalPowerDisplay === VenusOS.ElectricalPowerDisplay_PreferAmps
				 || Global.systemSettings.electricalPowerDisplay === VenusOS.ElectricalPowerDisplay_Mixed)
			statusText: !statusItem.valid ? ""
				: device.serviceType === "dcdc" ? VenusOS.system_stateToText(statusItem.value)
				: ""

			onClicked: root._showSettingsPage(device)

			VeQuickItem {
				id: temperatureItem
				uid: device.serviceUid + "/Dc/0/Temperature"
			}

			VeQuickItem {
				id: statusItem
				uid: device.serviceType === "dcdc" ? device.serviceUid + "/State" : ""
			}

			VeQuickItem {
				id: connectedItem
				uid: device.serviceUid + "/Connected"
			}

			VeQuickItem {
				id: showUnavailableItem
				uid: device.serviceUid + "/WengaoShowUnavailable"
			}

			DcDevice {
				id: dcDevice
				serviceUid: deviceDelegate.device.serviceUid
			}
		}
	}
}
