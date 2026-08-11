/*
** Copyright (C) 2025 Victron Energy B.V.
** See LICENSE.txt for license information.
**
** This code is based on Victron Energy code.
** Modified by the dbus-wengao contributors to show ordered Wengao terminal currents and
** configured offline devices without changing Victron's system total.
*/

import QtQuick
import Victron.VenusOS

Page {
	id: root

	function includeNonWengaoDevice(_device, childItems) {
		return childItems["WengaoShowUnavailable"]?.value !== 1
	}

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

				implicitHeight: wengaoTable.y + wengaoTable.height
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
					id: wengaoTable

					anchors.top: loadSummary.bottom
					width: parent.width
					rightPadding: loadSummary.rightPadding
					equalWidthColumns: true
					model: wengaoDevices.rowCount > 0 ? wengaoDevices : null
					delegate: Column {
						id: wengaoDeviceRows

						required property int index
						required property VeQItem item
						readonly property string serviceUid: item.itemParent().uid
						readonly property bool displayOfflineAsZero: showUnavailableItem.valid
								&& showUnavailableItem.value === 1
								&& connectedItem.value !== 1

						width: wengaoTable.width
						height: childrenRect.height

						QuantityTable.TableRow {
							table: wengaoTable
							index: wengaoDeviceRows.index * 3
							headerText: customNameItem.value || productNameItem.value || wengaoDeviceRows.serviceUid
							model: QuantityObjectModel {
								QuantityObject { object: dcDevice; key: "voltage"; unit: VenusOS.Units_Volt_DC }
								QuantityObject { object: dcDevice; key: "current"; unit: VenusOS.Units_Amp }
								QuantityObject { object: displayDevice; key: "power"; unit: VenusOS.Units_Watt }
							}
						}

						QuantityTable.TableRow {
							table: wengaoTable
							index: wengaoDeviceRows.index * 3 + 1
							headerText: qsTr("Terminal A")
							headerColor: Theme.color_font_secondary
							model: QuantityObjectModel {
								QuantityObject { unit: VenusOS.Units_Volt_DC; hidden: true }
								QuantityObject { object: terminalACurrentItem; unit: VenusOS.Units_Amp }
								QuantityObject { unit: VenusOS.Units_Watt; hidden: true }
							}
						}

						QuantityTable.TableRow {
							table: wengaoTable
							index: wengaoDeviceRows.index * 3 + 2
							headerText: qsTr("Terminal B")
							headerColor: Theme.color_font_secondary
							model: QuantityObjectModel {
								QuantityObject { unit: VenusOS.Units_Volt_DC; hidden: true }
								QuantityObject { object: terminalBCurrentItem; unit: VenusOS.Units_Amp }
								QuantityObject { unit: VenusOS.Units_Watt; hidden: true }
							}
						}

						QtObject {
							id: displayDevice
							readonly property real power: wengaoDeviceRows.displayOfflineAsZero
									|| !dcLoadPowerItem.valid ? 0 : dcLoadPowerItem.value
						}

						DcDevice {
							id: dcDevice
							serviceUid: wengaoDeviceRows.serviceUid
						}

						VeQuickItem {
							id: dcLoadPowerItem
							uid: wengaoDeviceRows.serviceUid + "/Wengao/DcLoadPower"
						}

						VeQuickItem {
							id: terminalACurrentItem
							uid: wengaoDeviceRows.serviceUid + "/Wengao/TerminalA/SignedCurrent"
						}

						VeQuickItem {
							id: terminalBCurrentItem
							uid: wengaoDeviceRows.serviceUid + "/Wengao/TerminalB/SignedCurrent"
						}

						VeQuickItem {
							id: customNameItem
							uid: wengaoDeviceRows.serviceUid + "/CustomName"
						}

						VeQuickItem {
							id: productNameItem
							uid: wengaoDeviceRows.serviceUid + "/ProductName"
						}

						VeQuickItem {
							id: connectedItem
							uid: wengaoDeviceRows.serviceUid + "/Connected"
						}

						VeQuickItem {
							id: showUnavailableItem
							uid: wengaoDeviceRows.serviceUid + "/WengaoShowUnavailable"
						}
					}
				}
			}
		}
	}

	GradientListView {
		header: wengaoDevices.rowCount > 0 ? headerComponent : null
		model: nonWengaoDevices
		delegate: LoadListDelegate {
			id: deviceDelegate

			required property var device

			name: device.name
			power: dcDevice.power ?? NaN
			current: dcDevice.current ?? NaN
			temperature: temperatureItem.value ?? NaN
			columnWidth: ListView.view.headerItem?.contentItem?.columnWidth ?? Theme.geometry_loadListPage_defaultColumnWidth
			columnSpacing: ListView.view.headerItem?.contentItem?.columnSpacing ?? Theme.geometry_quantityTable_horizontalSpacing_large
			unitAmps: wengaoDevices.rowCount === 0 && !isNaN(current)
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

			DcDevice {
				id: dcDevice
				serviceUid: deviceDelegate.device.serviceUid
			}
		}
	}

	// These models must belong to the detail page. Models owned by the overview widget are
	// disabled when that page leaves the stack, which previously made this table empty.
	VeQItemSortTableModel {
		id: wengaoDevices
		dynamicSortFilter: true
		filterRole: VeQItemTableModel.ValueRole
		filterFlags: VeQItemSortTableModel.FilterInvalid
		sortColumn: orderedChildren.sortValueColumn

		model: VeQItemChildModel {
			id: orderedChildren
			childId: "WengaoDisplayOrder"
			model: VeQItemFilteredServiceModel {
				serviceTypes: ["alternator", "dcsystem", "dcload", "dcdc", "motordrive"]
			}
			sortDelegate: VeQItemSortDelegate {
				VeQuickItem {
					id: displayOrderItem
					uid: buddy.uid + "/WengaoDisplayOrder"
				}
				sortValue: displayOrderItem.valid ? displayOrderItem.value : 2147483647
			}
		}
	}

	FilteredDeviceModel {
		id: nonWengaoDevices
		serviceTypes: ["dcsystem", "dcload", "dcdc", "motordrive"]
		childFilterIds: {
			"dcsystem": ["WengaoShowUnavailable"],
			"dcload": ["WengaoShowUnavailable"],
			"dcdc": ["WengaoShowUnavailable"],
			"motordrive": ["WengaoShowUnavailable"]
		}
		childFilterFunction: root.includeNonWengaoDevice
	}
}
