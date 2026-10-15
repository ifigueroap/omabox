import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Commons as Commons
import "logic.js" as Logic

PanelWindow {
  id: window

  required property var host
  property bool tipOpen: false
  property string tipText: ""
  property real tipY: 0
  property bool latched: false

  readonly property string presentation: Logic.dockPresentation(
    window.host && window.host.dockMode ? window.host.dockMode : "always",
    window.host ? window.host.omaboxActive === true : false,
    latched
  )

  function setLatched(inside) {
    if (inside) {
      collapseTimer.stop()
      latched = true
      return
    }
    collapseTimer.restart()
  }

  Timer {
    id: collapseTimer
    interval: 400
    repeat: false
    onTriggered: window.latched = false
  }

  visible: presentation !== "hidden"
  color: "transparent"
  exclusionMode: ExclusionMode.Normal
  // Reserve space only while the Omabox workspace is showing the full dock.
  // On a regular workspace the notch and the hover expansion overlay the edge.
  exclusiveZone: presentation === "full" && window.host && window.host.omaboxActive === true ? chrome.width : 0
  WlrLayershell.namespace: "omabox-dock"
  WlrLayershell.layer: WlrLayer.Top
  WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

  anchors {
    top: true
    bottom: true
    right: true
  }

  implicitWidth: Style.space(240)

  mask: Region {
    item: chrome
    Region { item: window.presentation === "full" && window.tipOpen ? tip : null }
  }

  function unreadFor(service) {
    var best = 0
    var rows = window.host ? window.host.windows : ({})
    for (var address in rows) {
      var row = rows[address]
      if (!row || row.className !== service.class) continue
      var count = Logic.unreadCount(row.title, service.unread)
      if (count > best) best = count
    }
    return best
  }

  function urgentFor(service) {
    var rows = window.host ? window.host.windows : ({})
    for (var address in rows) {
      var row = rows[address]
      if (row && row.className === service.class && row.urgent) return true
    }
    return false
  }

  function runningFor(service) {
    var rows = window.host ? window.host.windows : ({})
    for (var address in rows) {
      if (rows[address] && rows[address].className === service.class) return true
    }
    return false
  }

  Rectangle {
    id: tip
    visible: window.tipOpen && window.tipText !== ""
    x: chrome.x - width - Style.spacing.sm
    y: Math.max(Style.spacing.sm, Math.min(window.height - height - Style.spacing.sm, window.tipY))
    width: tipLabel.implicitWidth + Style.spacing.controlPaddingX * 2
    height: tipLabel.implicitHeight + Style.spacing.controlPaddingY * 2
    radius: Style.space(6)
    color: Commons.Color.tooltip.background
    border.color: Commons.Color.tooltip.border
    border.width: Style.normalBorderWidth

    Text {
      id: tipLabel
      anchors.centerIn: parent
      textFormat: Text.PlainText
      text: window.tipText
      color: Commons.Color.tooltip.text
      font.family: Style.font.family
      font.pixelSize: Style.font.body
    }
  }

  Item {
    id: chrome
    anchors.right: parent.right
    anchors.rightMargin: Style.spacing.xs
    anchors.verticalCenter: parent.verticalCenter
    width: window.presentation === "full" ? pill.width : Math.max(notch.width, Style.space(16))
    height: window.presentation === "full" ? pill.height : notch.height

    Behavior on width {
      NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
    }
    Behavior on height {
      NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
    }

    HoverHandler {
      onHoveredChanged: window.setLatched(hovered)
    }

    Rectangle {
      id: notch
      visible: window.presentation !== "full"
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      width: Style.space(8)
      height: Style.space(56)
      radius: width / 2
      color: Commons.Color.background
      border.color: Commons.Color.popups.border
      border.width: Style.normalBorderWidth
    }

  Rectangle {
    id: pill
    visible: window.presentation === "full"
    anchors.right: parent.right
    anchors.verticalCenter: parent.verticalCenter
    width: column.implicitWidth + Style.spacing.sm * 2
    height: column.implicitHeight + Style.spacing.sm * 2
    radius: Math.max(Style.cornerRadius, Style.space(12))
    color: Commons.Color.background
    border.color: Commons.Color.popups.border
    border.width: Style.normalBorderWidth

    Column {
      id: column
      anchors.centerIn: parent
      spacing: Style.spacing.xs

      Repeater {
        model: window.host ? window.host.services : []

        delegate: Item {
          id: slot
          required property var modelData
          width: Style.space(40)
          height: Style.space(40)

          readonly property int unread: window.host && window.host.windows ? window.unreadFor(modelData) : 0
          readonly property bool urgent: window.host && window.host.windows ? window.urgentFor(modelData) : false
          readonly property bool running: window.host && window.host.windows ? window.runningFor(modelData) : false
          readonly property string letter: modelData.name ? String(modelData.name).charAt(0) : "?"

          Rectangle {
            anchors.fill: parent
            radius: Style.space(8)
            color: mouse.containsMouse ? Commons.Color.menu.selectedBackground : "transparent"
          }

          Image {
            id: icon
            anchors.centerIn: parent
            width: Style.space(26)
            height: Style.space(26)
            source: modelData.icon ? Util.fileUrl(modelData.icon) : ""
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            sourceSize.width: Style.space(52)
            sourceSize.height: Style.space(52)
            opacity: modelData.ready ? 1 : 0.4
          }

          Text {
            anchors.centerIn: parent
            visible: icon.status !== Image.Ready
            textFormat: Text.PlainText
            text: slot.letter
            color: modelData.ready ? Commons.Color.foreground : Commons.Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.title
            font.bold: true
          }

          Rectangle {
            visible: slot.running
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(3)
            height: Style.space(14)
            radius: width
            color: Commons.Color.accent
          }

          Rectangle {
            id: badge
            visible: slot.unread > 0 || (slot.urgent && slot.unread === 0)
            anchors.right: parent.right
            anchors.top: parent.top
            width: slot.unread > 0 ? Math.max(Style.space(16), badgeText.implicitWidth + Style.spacing.xs * 2) : Style.space(10)
            height: slot.unread > 0 ? Style.space(16) : Style.space(10)
            radius: height / 2
            color: Commons.Color.urgent

            Text {
              id: badgeText
              anchors.centerIn: parent
              visible: slot.unread > 0
              text: slot.unread > 99 ? "99+" : String(slot.unread)
              color: Commons.Color.background
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              font.bold: true
            }
          }

          MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            onContainsMouseChanged: {
              window.tipOpen = containsMouse
              window.tipText = slot.modelData.name || ""
              window.tipY = slot.mapToItem(window.contentItem, 0, slot.height / 2).y - tip.height / 2
            }
            onClicked: {
              if (!slot.modelData.ready) {
                window.host.open("{}")
                return
              }
              window.host.run(["focus", slot.modelData.id])
            }
          }
        }
      }

      Rectangle {
        width: Style.space(40)
        height: Style.space(32)
        radius: Style.space(8)
        color: addMouse.containsMouse ? Commons.Color.menu.selectedBackground : "transparent"

        Text {
          anchors.centerIn: parent
          text: "+"
          color: Commons.Color.foreground
          font.family: Style.font.family
          font.pixelSize: Style.font.heading
        }

        MouseArea {
          id: addMouse
          anchors.fill: parent
          hoverEnabled: true
          onClicked: window.host.open("{}")
        }
      }
    }
  }
  }
}
