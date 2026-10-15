import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Commons as Commons

PanelWindow {
  id: dashboard

  required property var host
  property bool shown: false

  visible: shown
  color: "transparent"
  exclusionMode: ExclusionMode.Ignore
  exclusiveZone: 0
  WlrLayershell.namespace: "omabox-dashboard"
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: shown ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

  anchors {
    top: true
    bottom: true
    right: true
  }

  implicitWidth: Style.space(420) + Style.space(72)

  mask: Region {
    item: card
  }

  property string formName: ""
  property string formUrl: ""
  property string formProfile: ""
  property string formKey: ""
  property string formId: ""
  readonly property var dockChoices: [
    { "mode": "always", "label": "Always" },
    { "mode": "special-only", "label": "Workspace only" }
  ]

  function fillPreset(service) {
    formId = service.id
    nameField.text = service.name
    urlField.text = service.url
    profileField.text = service.profile
    keyField.text = service.key
  }

  function submit() {
    formName = nameField.text
    formUrl = urlField.text
    formProfile = profileField.text
    formKey = keyField.text
    if (!formName && !formId) return
    var args = ["add", "--update"]
    if (formId) args.push("--id", formId)
    if (formName) args.push("--name", formName)
    args.push("--url", formUrl)
    if (formProfile) args.push("--profile", formProfile)
    if (formKey) args.push("--key", formKey)
    host.run(args)
    host.reloadServices()
  }

  Rectangle {
    id: card
    focus: true
    Keys.onEscapePressed: dashboard.shown = false
    anchors.fill: parent
    anchors.rightMargin: Style.space(72)
    anchors.topMargin: Style.gapsOut
    anchors.bottomMargin: Style.gapsOut
    radius: Math.max(Style.cornerRadius, Style.space(12))
    color: Commons.Color.popups.background
    border.color: Commons.Color.popups.border
    border.width: Style.normalBorderWidth

    ColumnLayout {
      anchors.fill: parent
      anchors.margins: Style.spacing.panelPadding
      spacing: Style.spacing.rowGap

      RowLayout {
        Layout.fillWidth: true
        Text {
          textFormat: Text.PlainText
          text: "Omabox"
          color: Commons.Color.popups.text
          font.family: Style.font.family
          font.pixelSize: Style.font.heading
          font.bold: true
          Layout.fillWidth: true
        }
        Text {
          text: "esc"
          color: Commons.Color.muted
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
        }
      }

      Text {
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: "Services share one Chromium (--user-data-dir) and keep a profile each. Super+Shift+O toggles the workspace. The bar icon does the same."
        color: Commons.Color.muted
        font.family: Style.font.family
        font.pixelSize: Style.font.bodySmall
      }

      RowLayout {
        Layout.fillWidth: true
        spacing: Style.spacing.xs
        Text {
          textFormat: Text.PlainText
          text: "Dock"
          color: Commons.Color.popups.text
          font.family: Style.font.family
          font.pixelSize: Style.font.body
        }
        Repeater {
          model: dashboard.dockChoices
          delegate: Rectangle {
            required property var modelData
            readonly property bool selected: dashboard.host && dashboard.host.dockMode === modelData.mode
            Layout.preferredHeight: Style.spacing.controlHeight
            Layout.preferredWidth: label.implicitWidth + Style.spacing.controlPaddingX * 2
            radius: Style.space(6)
            color: selected ? Commons.Color.menu.selectedBackground : "transparent"
            border.color: Commons.Color.popups.border
            border.width: Style.normalBorderWidth

            Text {
              id: label
              anchors.centerIn: parent
              textFormat: Text.PlainText
              text: modelData.label
              color: Commons.Color.popups.text
              font.family: Style.font.family
              font.pixelSize: Style.font.bodySmall
            }

            MouseArea {
              anchors.fill: parent
              onClicked: {
                if (!dashboard.host) return
                dashboard.host.run(["config", "dock", modelData.mode])
              }
            }
          }
        }
      }

      Flickable {
        Layout.fillWidth: true
        Layout.fillHeight: true
        contentHeight: serviceColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
          id: serviceColumn
          width: parent.width
          spacing: Style.spacing.xs

          Repeater {
            model: dashboard.host ? dashboard.host.services : []
            delegate: Rectangle {
              required property var modelData
              width: serviceColumn.width
              height: Style.spacing.controlHeight + Style.spacing.sm
              radius: Style.space(6)
              color: rowMouse.containsMouse ? Commons.Color.menu.selectedBackground : "transparent"

              RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Style.spacing.rowPaddingX
                anchors.rightMargin: Style.spacing.xs
                spacing: Style.spacing.labelGap

                Text {
                  textFormat: Text.PlainText
                  text: modelData.key ? modelData.key : "·"
                  color: Commons.Color.accent
                  font.family: Style.font.family
                  font.pixelSize: Style.font.body
                  Layout.preferredWidth: Style.space(16)
                }
                ColumnLayout {
                  Layout.fillWidth: true
                  spacing: 0
                  Text {
                    textFormat: Text.PlainText
                    text: modelData.name
                    color: Commons.Color.popups.text
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                  }
                  Text {
                    textFormat: Text.PlainText
                    text: modelData.ready ? modelData.url : "Needs a URL"
                    color: Commons.Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                  }
                }
                Text {
                  text: "remove"
                  color: Commons.Color.urgent
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  MouseArea {
                    id: removeMouse
                    anchors.fill: parent
                    anchors.margins: -Style.spacing.sm
                    onClicked: {
                      dashboard.host.run(["remove", modelData.id])
                      dashboard.host.reloadServices()
                    }
                  }
                }
              }

              MouseArea {
                id: rowMouse
                anchors.fill: parent
                anchors.rightMargin: Style.space(64)
                hoverEnabled: true
                onClicked: dashboard.fillPreset(modelData)
              }
            }
          }
        }
      }

      Text {
        text: "Add or update"
        color: Commons.Color.popups.text
        font.family: Style.font.family
        font.pixelSize: Style.font.subtitle
      }

      Flow {
        Layout.fillWidth: true
        spacing: Style.spacing.xs

        Repeater {
          model: ["whatsapp", "slack", "discord", "zulip", "telegram", "grok", "chatgpt", "claude", "grok-bot"]
          delegate: Rectangle {
            required property var modelData
            width: chip.implicitWidth + Style.spacing.controlPaddingX * 2
            height: Style.spacing.controlHeight
            radius: height / 2
            color: chipMouse.containsMouse ? Commons.Color.accent : Commons.Color.menu.selectedBackground

            Text {
              id: chip
              anchors.centerIn: parent
              text: modelData
              color: Commons.Color.popups.text
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
            }

            MouseArea {
              id: chipMouse
              anchors.fill: parent
              hoverEnabled: true
              onClicked: {
                var services = dashboard.host.services
                for (var i = 0; i < services.length; i++) {
                  if (services[i].id === modelData) {
                    dashboard.fillPreset(services[i])
                    return
                  }
                }
                dashboard.host.run(["add", modelData])
              }
            }
          }
        }
      }

      GridLayout {
        columns: 2
        columnSpacing: Style.spacing.labelGap
        rowSpacing: Style.spacing.labelGap
        Layout.fillWidth: true

        Text { text: "Name"; color: Commons.Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption }
        TextField {
          id: nameField
          Layout.fillWidth: true
          placeholderText: "Work chat"
          color: Commons.Color.popups.text
          font.family: Style.font.family
          font.pixelSize: Style.font.body
          background: Rectangle {
            color: Commons.Color.background
            radius: Style.space(4)
            border.color: Commons.Color.popups.border
            border.width: Style.normalBorderWidth
          }
        }
        Text { text: "URL"; color: Commons.Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption }
        TextField {
          id: urlField
          Layout.fillWidth: true
          placeholderText: "https://"
          color: Commons.Color.popups.text
          font.family: Style.font.family
          font.pixelSize: Style.font.body
          background: Rectangle {
            color: Commons.Color.background
            radius: Style.space(4)
            border.color: Commons.Color.popups.border
            border.width: Style.normalBorderWidth
          }
        }
        Text { text: "Profile"; color: Commons.Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption }
        TextField {
          id: profileField
          Layout.fillWidth: true
          placeholderText: "Profile name"
          color: Commons.Color.popups.text
          font.family: Style.font.family
          font.pixelSize: Style.font.body
          background: Rectangle {
            color: Commons.Color.background
            radius: Style.space(4)
            border.color: Commons.Color.popups.border
            border.width: Style.normalBorderWidth
          }
        }
        Text { text: "Key"; color: Commons.Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption }
        TextField {
          id: keyField
          Layout.preferredWidth: Style.space(80)
          placeholderText: "1-9"
          color: Commons.Color.popups.text
          font.family: Style.font.family
          font.pixelSize: Style.font.body
          background: Rectangle {
            color: Commons.Color.background
            radius: Style.space(4)
            border.color: Commons.Color.popups.border
            border.width: Style.normalBorderWidth
          }
        }
      }

      RowLayout {
        Layout.alignment: Qt.AlignRight
        spacing: Style.spacing.sm

        Rectangle {
          width: saveLabel.implicitWidth + Style.spacing.controlPaddingX * 2
          height: Style.spacing.controlHeight
          radius: Style.space(6)
          color: saveMouse.containsMouse ? Commons.Color.accent : Commons.Color.menu.selectedBackground
          Text {
            id: saveLabel
            anchors.centerIn: parent
            text: "Save"
            color: Commons.Color.popups.text
            font.family: Style.font.family
            font.pixelSize: Style.font.body
          }
          MouseArea {
            id: saveMouse
            anchors.fill: parent
            hoverEnabled: true
            onClicked: dashboard.submit()
          }
        }
      }
    }
  }

  onShownChanged: if (shown) card.forceActiveFocus()
}
