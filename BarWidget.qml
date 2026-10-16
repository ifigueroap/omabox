import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import "logic.js" as Logic

// Bar slot for a third-party plugin. qs.Ui.BarWidget and qs.Ui.WidgetButton
// are component types, and those are not visible to a file under
// ~/.config/omarchy/plugins/ (the same limit as ShellIpc). The bar host
// injects `bar` (PluginBarApi for third-party widgets) and calls
// triggerPress on the widget item itself.
Item {
  id: root

  property var bar: null
  property var manifest: null
  property string moduleName: "omabox"
  property var settings: ({})
  property bool interactive: true
  property bool pressable: true

  property var services: []
  property var windows: ({})
  property bool doNotDisturb: false

  readonly property int unreadTotal: Logic.totalUnread(services, windows, doNotDisturb)
  readonly property string unreadText: Logic.unreadLabel(unreadTotal)
  readonly property string home: Quickshell.env("HOME")
  readonly property string configPath: home + "/.config/omabox/services.toml"
  // Same lookup as Panel.qml. The bar entry may not receive manifest; the
  // document URL still resolves bin/omabox next to this file.
  readonly property string cliPath: {
    var dir = manifest && manifest.__sourceDir ? String(manifest.__sourceDir) : ""
    if (dir.length > 0) return dir.replace(/\/$/, "") + "/bin/omabox"
    var url = Qt.resolvedUrl("bin/omabox").toString()
    if (url.indexOf("file://") === 0)
      url = decodeURIComponent(url.replace(/^file:\/\//, ""))
    return url
  }

  implicitWidth: unreadTotal > 0
    ? Style.space(8) + Style.space(14) + Style.space(4) + badge.width + Style.space(6)
    : Style.space(32)
  implicitHeight: Style.space(32)

  function triggerPress(button) {
    if (button !== Qt.LeftButton) return
    if (root.bar && root.bar.hideTooltip) root.bar.hideTooltip(root)
    if (root.bar && root.bar.run) root.bar.run("omabox toggle")
  }

  function tooltipText() {
    if (root.unreadTotal > 0) return "Omabox (" + root.unreadText + ")"
    return "Omabox"
  }

  function reloadServices() {
    if (!root.cliPath || listProc.running) return
    listProc.running = true
  }

  function applyList(raw) {
    try {
      var data = JSON.parse(raw || "{}")
      root.services = data && data.services ? data.services : []
      if (data && (data.dnd === true || data.dnd === false))
        root.doNotDisturb = data.dnd
    } catch (error) {
      console.warn("omabox: service list is not JSON")
    }
  }

  function syncToplevels() {
    var values = []
    if (Hyprland.toplevels && Hyprland.toplevels.values)
      values = Hyprland.toplevels.values
    root.windows = Logic.syncToplevels(root.windows, values)
  }

  function handleEvent(event) {
    if (!event || !event.name) return
    var name = String(event.name)
    if (name === "openwindow" || name === "windowtitle") root.syncToplevels()
    else root.windows = Logic.handleWindowEvent(root.windows, event)
  }

  HoverHandler {
    onHoveredChanged: {
      if (!root.bar) return
      if (hovered && root.bar.showTooltip) root.bar.showTooltip(root, root.tooltipText())
      else if (root.bar.hideTooltip) root.bar.hideTooltip(root)
    }
  }

  Item {
    id: mark
    anchors.left: parent.left
    anchors.leftMargin: Style.space(8)
    anchors.verticalCenter: parent.verticalCenter
    width: Style.space(14)
    height: Style.space(14)

    Rectangle {
      anchors.fill: parent
      radius: Style.space(3)
      color: "transparent"
      border.color: root.bar ? root.bar.foreground : Commons.Color.foreground
      border.width: Math.max(1, Style.normalBorderWidth)
    }

    Rectangle {
      anchors.centerIn: parent
      width: Style.space(4)
      height: Style.space(4)
      radius: width / 2
      color: root.bar ? root.bar.foreground : Commons.Color.foreground
    }
  }

  Rectangle {
    id: badge
    visible: root.unreadTotal > 0
    anchors.left: mark.right
    anchors.leftMargin: Style.space(4)
    anchors.verticalCenter: parent.verticalCenter
    width: root.unreadTotal > 0
      ? Math.max(Style.space(16), badgeText.implicitWidth + Style.spacing.xs * 2)
      : 0
    height: Style.space(16)
    radius: height / 2
    color: Commons.Color.urgent

    Text {
      id: badgeText
      anchors.centerIn: parent
      visible: root.unreadTotal > 0
      textFormat: Text.PlainText
      text: root.unreadText
      color: Commons.Color.background
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
      font.bold: true
    }
  }

  FileView {
    id: configFile
    path: root.configPath
    watchChanges: true
    printErrors: false
    onLoaded: root.reloadServices()
    onFileChanged: reload()
  }

  Process {
    id: listProc
    command: [root.cliPath, "list", "--json"]
    stdout: StdioCollector {
      onStreamFinished: root.applyList(text)
    }
  }

  Connections {
    target: Hyprland
    function onRawEvent(event) { root.handleEvent(event) }
  }

  readonly property int toplevelCount: Hyprland.toplevels ? Hyprland.toplevels.values.length : 0
  onToplevelCountChanged: syncToplevels()

  Component.onCompleted: {
    reloadServices()
    syncToplevels()
  }
}
