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

	//% "DC Loads"
	title: qsTrId("overview_widget_dcloads_title")
	type: VenusOS.OverviewWidget_Type_DcLoads
	enabled: systemLoadDevices.count > 1 || nonSystemLoadDevices.count > 0
	preferredSize: loadDevices.count > 1 ? VenusOS.OverviewWidget_PreferredSize_PreferLarge : VenusOS.OverviewWidget_PreferredSize_Any

	contentItem: ColumnLayout {
		spacing: Theme.geometry_overviewPage_widget_content_spacing

		RowLayout {
			Layout.fillWidth: true

			WidgetHeader {
				text: root.title
				icon.source: "qrc:/images/dcloads.svg"
				Layout.fillWidth: true
			}

			OverviewElectricalQuantityLabel {
				widgetSize: VenusOS.OverviewWidget_Size_XS
				dataObject: Global.system.dc
				sourceType: VenusOS.ElectricalQuantity_Source_Dc
				alignment: Qt.AlignRight
				font.pixelSize: root.tertiaryFontSize
				valueColor: Theme.color_font_secondary
				unitColor: Theme.color_font_secondary
			}
		}

		Repeater {
			model: loadDevices

			delegate: RowLayout {
				required property Device device

				Layout.fillWidth: true

				Label {
					text: device.name
					elide: Text.ElideRight
					font.pixelSize: Theme.font_overviewPage_widget_phase_minimumSize
					color: Theme.color_font_secondary
					Layout.fillWidth: true
				}

				ElectricalQuantityLabel {
					dataObject: dcLoadDevice
					sourceType: VenusOS.ElectricalQuantity_Source_Dc
					alignment: Qt.AlignRight
					font.pixelSize: Theme.font_overviewPage_widget_phase_minimumSize
					valueColor: Theme.color_font_secondary
					unitColor: Theme.color_font_secondary
				}

				DcDevice {
					id: dcLoadDevice
					serviceUid: device.serviceUid
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
	}

	FilteredDeviceModel {
		id: systemLoadDevices
		serviceTypes: ["dcsystem"]
	}

	FilteredDeviceModel {
		id: nonSystemLoadDevices
		serviceTypes: ["dcload", "dcdc", "motordrive"]
	}
}
