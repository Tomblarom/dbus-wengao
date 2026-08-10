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

	function includeNonWengaoDevice(_device, childItems) {
		const marker = childItems["WengaoShowUnavailable"]
		return !marker || !marker.valid
	}

	//% "DC Loads"
	title: qsTrId("overview_widget_dcloads_title")
	type: VenusOS.OverviewWidget_Type_DcLoads
	enabled: loadDevices.count > 0 || nonWengaoLoadDevices.count > 0
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

					required property VeQItem item
					readonly property string serviceUid: item.itemParent().uid
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
						text: (customNameItem.value || productNameItem.value || serviceUid) + ":"
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
									|| !dcLoadPowerItem.valid
									? 0
									: dcLoadPowerItem.value
							readonly property real current: NaN
						}
						sourceType: VenusOS.ElectricalQuantity_Source_Any
						alignment: Qt.AlignRight
						font.pixelSize: root.tertiaryFontSize
						valueColor: Theme.color_font_primary
						unitColor: Theme.color_font_secondary
					}

					VeQuickItem {
						id: dcLoadPowerItem
						uid: deviceDelegate.serviceUid + "/Wengao/DcLoadPower"
					}

					VeQuickItem {
						id: customNameItem
						uid: deviceDelegate.serviceUid + "/CustomName"
					}

					VeQuickItem {
						id: productNameItem
						uid: deviceDelegate.serviceUid + "/ProductName"
					}

					VeQuickItem {
						id: connectedItem
						uid: deviceDelegate.serviceUid + "/Connected"
					}

					VeQuickItem {
						id: showUnavailableItem
						uid: deviceDelegate.serviceUid + "/WengaoShowUnavailable"
					}
				}
			}
		}
	}

	onClicked: {
		Global.pageManager.pushPage("/pages/loads/DcLoadListPage.qml", {
			title: root.title,
			wengaoModel: loadDevices,
			nonWengaoModel: nonWengaoLoadDevices
		});
	}

	VeQItemSortTableModel {
		id: loadDevices
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
		id: nonWengaoLoadDevices
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
