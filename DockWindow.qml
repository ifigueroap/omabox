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
  property real tipX: 0
  property real tipY: 0
  property bool latched: false
  property bool menuOpen: false
  property string menuServiceId: ""
  property var menuAnchor: null
  property real menuX: 0
  property real menuY: 0

  readonly property string edge: {
    var value = window.host && window.host.dockEdge ? String(window.host.dockEdge) : "right"
    if (value === "left" || value === "right" || value === "top" || value === "bottom")
      return value
    return "right"
  }
  readonly property bool horizontal: edge === "top" || edge === "bottom"
  readonly property bool pinned: window.host ? window.host.dockPinned === true : false
  readonly property bool onOmabox: window.host ? window.host.omaboxActive === true : false

  readonly property string presentation: Logic.dockPresentation(
    window.host && window.host.dockMode ? window.host.dockMode : "always",
    onOmabox,
    latched,
    pinned
  )

  function setLatched(inside) {
    if (inside || window.menuOpen) {
      collapseTimer.stop()
      latched = true
      return
    }
    collapseTimer.restart()
  }

  function placeTip(slot) {
    window.placeTipItem(slot, slot.modelData.name || "")
  }

  function placeTipItem(slot, text) {
    if (window.menuOpen) return
    window.tipText = text
    window.tipOpen = true
    var center = slot.mapToItem(window.contentItem, slot.width / 2, slot.height / 2)
    var gap = Style.spacing.sm
    var x = 0
    var y = 0
    if (window.edge === "left") {
      x = chrome.x + chrome.width + gap
      y = center.y - tip.height / 2
    } else if (window.edge === "top") {
      x = center.x - tip.width / 2
      y = chrome.y + chrome.height + gap
    } else if (window.edge === "bottom") {
      x = center.x - tip.width / 2
      y = chrome.y - tip.height - gap
    } else {
      x = chrome.x - tip.width - gap
      y = center.y - tip.height / 2
    }
    window.tipX = Math.max(gap, Math.min(window.width - tip.width - gap, x))
    window.tipY = Math.max(gap, Math.min(window.height - tip.height - gap, y))
  }

  function placeMenu(slot) {
    if (!slot) return
    var gap = Style.spacing.sm
    var menuWidth = menu.width > 0 ? menu.width : Style.space(148)
    var menuHeight = menu.height > 0 ? menu.height : Style.space(80)
    var center = slot.mapToItem(window.contentItem, slot.width / 2, slot.height / 2)
    var x = 0
    var y = 0
    if (window.edge === "left") {
      x = chrome.x + chrome.width + gap
      y = center.y - menuHeight / 2
    } else if (window.edge === "top") {
      x = center.x - menuWidth / 2
      y = chrome.y + chrome.height + gap
    } else if (window.edge === "bottom") {
      x = center.x - menuWidth / 2
      y = chrome.y - menuHeight - gap
    } else {
      x = chrome.x - menuWidth - gap
      y = center.y - menuHeight / 2
    }
    window.menuX = Math.max(gap, Math.min(window.width - menuWidth - gap, x))
    window.menuY = Math.max(gap, Math.min(window.height - menuHeight - gap, y))
  }

  function openMenu(slot) {
    window.tipOpen = false
    window.menuAnchor = slot
    window.menuServiceId = String(slot.modelData.id || "")
    window.menuOpen = true
    collapseTimer.stop()
    window.latched = true
    window.placeMenu(slot)
  }

  readonly property var menuService: {
    var id = window.menuServiceId
    var rows = window.host && window.host.services ? window.host.services : []
    for (var i = 0; i < rows.length; i++) {
      if (rows[i] && rows[i].id === id) return rows[i]
    }
    return null
  }
  readonly property var menuItems: Logic.serviceMenuItems(window.menuService)

  onMenuOpenChanged: {
    if (!menuOpen && (!edgeHover || !edgeHover.hovered)) collapseTimer.restart()
  }

  onPresentationChanged: {
    if (presentation !== "full") menuOpen = false
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
  exclusiveZone: presentation === "full" && onOmabox ? (horizontal ? chrome.height : chrome.width) : 0
  WlrLayershell.namespace: "omabox-dock"
  WlrLayershell.layer: WlrLayer.Top
  WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

  anchors.top: edge !== "bottom"
  anchors.bottom: edge !== "top"
  anchors.left: edge !== "right"
  anchors.right: edge !== "left"

  implicitWidth: Style.space(240)
  implicitHeight: Style.space(240)

  mask: Region {
    item: chrome
    Region { item: window.presentation === "full" && window.tipOpen && !window.menuOpen ? tip : null }
    Region { item: window.presentation === "full" && window.menuOpen ? menu : null }
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

  Item {
    id: stage
    anchors.fill: parent

      Rectangle {
        id: tip
        visible: window.tipOpen && window.tipText !== "" && !window.menuOpen
      x: window.tipX
      y: window.tipY
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
      x: {
        if (window.edge === "left") return Style.spacing.xs
        if (window.edge === "right") return Math.max(0, stage.width - width - Style.spacing.xs)
        return Math.max(0, (stage.width - width) / 2)
      }
      y: {
        if (window.edge === "top") return Style.spacing.xs
        if (window.edge === "bottom") return Math.max(0, stage.height - height - Style.spacing.xs)
        return Math.max(0, (stage.height - height) / 2)
      }
      width: window.presentation === "full"
        ? pill.width
        : (window.horizontal ? notch.width : Math.max(notch.width, Style.space(16)))
      height: window.presentation === "full"
        ? pill.height
        : (window.horizontal ? Math.max(notch.height, Style.space(16)) : notch.height)
      opacity: Logic.dockOpacity(edgeHover.hovered, window.pinned, window.onOmabox)

      Behavior on width {
        NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
      }
      Behavior on height {
        NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
      }
      Behavior on opacity {
        NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
      }

      HoverHandler {
        id: edgeHover
        onHoveredChanged: window.setLatched(hovered)
      }

      Rectangle {
        id: notch
        visible: window.presentation !== "full"
        x: window.edge === "left" ? 0 : (window.horizontal ? (parent.width - width) / 2 : parent.width - width)
        y: window.edge === "top" ? 0 : (window.horizontal ? parent.height - height : (parent.height - height) / 2)
        width: window.horizontal ? Style.space(56) : Style.space(8)
        height: window.horizontal ? Style.space(8) : Style.space(56)
        radius: Math.min(width, height) / 2
        color: Commons.Color.background
        border.color: Commons.Color.popups.border
        border.width: Style.normalBorderWidth
      }

      Rectangle {
        id: pill
        visible: window.presentation === "full"
        x: window.edge === "left" ? 0 : (window.horizontal ? 0 : parent.width - width)
        y: window.edge === "top" ? 0 : (window.horizontal ? parent.height - height : 0)
        width: icons.implicitWidth + Style.spacing.sm * 2
        height: icons.implicitHeight + Style.spacing.sm * 2
        radius: Math.max(Style.cornerRadius, Style.space(12))
        color: Commons.Color.background
        border.color: Commons.Color.popups.border
        border.width: Style.normalBorderWidth

        Grid {
          id: icons
          anchors.centerIn: parent
          columns: window.horizontal ? 32 : 1
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
              readonly property bool badgesOn: Logic.allowsBadges(modelData, window.host ? window.host.doNotDisturb : false)
              readonly property bool soundOn: Logic.allowsSound(modelData, window.host ? window.host.doNotDisturb : false)
              readonly property string letter: modelData.name ? String(modelData.name).charAt(0) : "?"
              property bool held: false
              property bool suppressHold: false

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
                visible: slot.badgesOn && (slot.unread > 0 || (slot.urgent && slot.unread === 0))
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
                  textFormat: Text.PlainText
                  text: slot.unread > 99 ? "99+" : String(slot.unread)
                  color: Commons.Color.background
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }
              }

              Rectangle {
                visible: !slot.soundOn
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                width: Style.space(8)
                height: Style.space(8)
                radius: width / 2
                color: Commons.Color.muted
              }

              MouseArea {
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                pressAndHoldInterval: 500
                onContainsMouseChanged: {
                  if (window.menuOpen) return
                  if (containsMouse) window.placeTip(slot)
                  else window.tipOpen = false
                }
                onPressed: function(mouseEvent) {
                  slot.suppressHold = false
                  if (mouseEvent.button !== Qt.RightButton) return
                  var id = String(slot.modelData.id || "")
                  if (window.menuOpen && window.menuServiceId === id) {
                    window.menuOpen = false
                    slot.suppressHold = true
                    return
                  }
                  window.openMenu(slot)
                }
                onPressAndHold: {
                  if (slot.suppressHold) return
                  slot.held = true
                  window.openMenu(slot)
                }
                onClicked: function(mouseEvent) {
                  if (slot.held) {
                    slot.held = false
                    return
                  }
                  if (mouseEvent.button !== Qt.LeftButton) return
                  window.menuOpen = false
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
              textFormat: Text.PlainText
              text: "+"
              color: Commons.Color.foreground
              font.family: Style.font.family
              font.pixelSize: Style.font.heading
            }

            MouseArea {
              id: addMouse
              anchors.fill: parent
              hoverEnabled: true
              onClicked: {
                window.menuOpen = false
                if (window.host) window.host.open("{}")
              }
            }
          }

          Item {
            width: window.horizontal ? Style.space(12) : Style.space(40)
            height: window.horizontal ? Style.space(32) : Style.space(12)

            Rectangle {
              anchors.centerIn: parent
              width: window.horizontal ? Math.max(1, Style.normalBorderWidth) : Style.space(20)
              height: window.horizontal ? Style.space(16) : Math.max(1, Style.normalBorderWidth)
              color: Commons.Color.popups.border
            }
          }

          Rectangle {
            id: dndSlot
            width: Style.space(40)
            height: Style.space(32)
            radius: Style.space(8)
            color: (dndMouse.containsMouse || (window.host && window.host.doNotDisturb))
                  ? Commons.Color.menu.selectedBackground
                  : "transparent"
            border.width: window.host && window.host.doNotDisturb ? Style.normalBorderWidth : 0
            border.color: Commons.Color.accent

            Text {
              anchors.centerIn: parent
              textFormat: Text.PlainText
              text: window.host && window.host.doNotDisturb ? "zZ" : "DND"
              color: window.host && window.host.doNotDisturb ? Commons.Color.accent : Commons.Color.muted
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              font.bold: window.host && window.host.doNotDisturb
            }

            MouseArea {
              id: dndMouse
              anchors.fill: parent
              hoverEnabled: true
              onContainsMouseChanged: {
                if (window.menuOpen) return
                if (containsMouse) window.placeTipItem(dndSlot, "Do not disturb")
                else window.tipOpen = false
              }
              onClicked: {
                window.menuOpen = false
                if (!window.host) return
                window.host.run(["config", "dnd", window.host.doNotDisturb ? "false" : "true"])
              }
            }
          }
        }
      }
    }

    Rectangle {
      id: menu
      visible: window.menuOpen && window.menuService
      x: window.menuX
      y: window.menuY
      z: 20
      readonly property int rows: window.menuItems ? window.menuItems.length : 0
      width: Style.space(164)
      height: rows * Style.spacing.controlHeight + Math.max(0, rows - 1) * Style.spacing.xs + Style.spacing.xs * 2
      radius: Style.space(6)
      color: Commons.Color.popups.background
      border.color: Commons.Color.popups.border
      border.width: Style.normalBorderWidth
      onWidthChanged: if (window.menuOpen && window.menuAnchor) window.placeMenu(window.menuAnchor)
      onHeightChanged: if (window.menuOpen && window.menuAnchor) window.placeMenu(window.menuAnchor)

      Column {
        id: menuColumn
        x: Style.spacing.xs
        y: Style.spacing.xs
        width: parent.width - Style.spacing.xs * 2
        spacing: Style.spacing.xs

        Repeater {
          model: window.menuItems
          delegate: Rectangle {
            required property var modelData
            width: menuColumn.width
            height: Style.spacing.controlHeight
            radius: Style.space(4)
            color: itemMouse.containsMouse ? Commons.Color.menu.selectedBackground : "transparent"

            Text {
              anchors.left: parent.left
              anchors.leftMargin: Style.spacing.sm
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: modelData.label
              color: Commons.Color.popups.text
              font.family: Style.font.family
              font.pixelSize: Style.font.body
            }
            Text {
              anchors.right: parent.right
              anchors.rightMargin: Style.spacing.sm
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: modelData.enabled ? "on" : "off"
              color: modelData.enabled ? Commons.Color.accent : Commons.Color.muted
              font.family: Style.font.family
              font.pixelSize: Style.font.body
            }

            MouseArea {
              id: itemMouse
              anchors.fill: parent
              hoverEnabled: true
              onClicked: {
                if (!window.host || !window.menuServiceId || !modelData.field) return
                window.host.run(["service", window.menuServiceId, modelData.field, modelData.next])
                window.menuOpen = false
              }
            }
          }
        }
      }
    }
  }
}
