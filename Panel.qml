import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import "logic.js" as Logic

// keepLoaded panel: shell/shell.qml mounts it at startup once the plugin is
// enabled, the same way omarchy.osd stays resident. Entry point is an Item.
// The host injects omarchyPath, shell, and manifest.
Item {
  id: root

  property string omarchyPath: ""
  property var shell: null
  property var manifest: null
  property bool opened: dashboard.shown

  property var services: []
  property var windows: ({})

  readonly property string home: Quickshell.env("HOME")
  readonly property string configPath: home + "/.config/omabox/services.toml"
  readonly property string cliPath: {
    var url = Qt.resolvedUrl("bin/omabox").toString()
    if (url.indexOf("file://") === 0)
      url = decodeURIComponent(url.slice("file://".length))
    return url
  }

  function open(payloadJson) {
    dashboard.shown = true
    reloadServices()
  }

  function close() {
    dashboard.shown = false
  }

  function reloadServices() {
    if (listProc.running) {
      listAgain.restart()
      return
    }
    listProc.running = true
  }

  function applyList(raw) {
    try {
      var data = JSON.parse(raw || "{}")
      root.services = data && data.services ? data.services : []
    } catch (error) {
      console.warn("omabox: service list is not JSON")
    }
  }

  function syncToplevels() {
    var values = []
    if (Hyprland.toplevels && Hyprland.toplevels.values)
      values = Hyprland.toplevels.values
    var next = {}
    var seen = {}
    for (var i = 0; i < values.length; i++) {
      var top = values[i]
      var ipc = top.lastIpcObject || {}
      var wayland = top.wayland || null
      var key = Logic.normAddress(ipc.address || top.address || "")
      if (!key) continue
      seen[key] = true
      var prev = root.windows[key] || null
      var wm = String(ipc.class || ipc.initialClass || (wayland && wayland.appId) || "")
      var title = String(ipc.title || ipc.initialTitle || "")
      next[key] = {
        className: wm || (prev ? prev.className : ""),
        title: title || (prev ? prev.title : ""),
        urgent: prev ? prev.urgent === true : false
      }
    }
    if (values.length === 0) {
      for (var kept in root.windows) next[kept] = root.windows[kept]
    }
    root.windows = next
  }

  function mergeWindow(address, patch) {
    var key = Logic.normAddress(address)
    if (!key) return
    var next = {}
    for (var existing in root.windows) next[existing] = root.windows[existing]
    var prev = next[key] || { className: "", title: "", urgent: false }
    next[key] = {
      className: patch.className !== undefined ? patch.className : prev.className,
      title: patch.title !== undefined ? patch.title : prev.title,
      urgent: patch.urgent !== undefined ? patch.urgent : prev.urgent
    }
    root.windows = next
  }

  function forgetWindow(address) {
    var key = Logic.normAddress(address)
    var next = {}
    for (var existing in root.windows) {
      if (existing !== key) next[existing] = root.windows[existing]
    }
    root.windows = next
  }

  function handleEvent(event) {
    if (!event || !event.name) return
    var name = String(event.name)
    var data = event.data !== undefined && event.data !== null ? String(event.data) : ""
    if (name === "windowtitlev2") {
      var parsed = Logic.eventTitle(data)
      mergeWindow(parsed.address, { title: parsed.title })
    } else if (name === "urgent") {
      mergeWindow(data, { urgent: true })
    } else if (name === "activewindowv2") {
      mergeWindow(data, { urgent: false })
    } else if (name === "closewindow") {
      forgetWindow(data)
    } else if (name === "openwindow" || name === "windowtitle") {
      syncToplevels()
    }
  }

  function run(args) {
    var argv = [root.cliPath]
    for (var i = 0; i < args.length; i++) argv.push(String(args[i]))
    Util.execArgv(argv)
  }

  Timer {
    id: listAgain
    interval: 150
    repeat: false
    onTriggered: root.reloadServices()
  }

  FileView {
    id: configFile
    path: root.configPath
    watchChanges: true
    printErrors: false
    onLoaded: root.reloadServices()
    onFileChanged: reload()
    onLoadFailed: initProc.running = true
  }

  Process {
    id: initProc
    command: [root.cliPath, "init"]
    onExited: root.reloadServices()
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

  ShellIpc {
    target: "omabox"

    function dashboard(): string {
      root.open("{}")
      return "ok"
    }

    function reload(): string {
      root.reloadServices()
      return "ok"
    }
  }

  Variants {
    model: Quickshell.screens
    delegate: Component {
      DockWindow {
        required property var modelData
        screen: modelData
        host: root
      }
    }
  }

  DashboardWindow {
    id: dashboard
    host: root
    screen: {
      var monitor = Hyprland.focusedMonitor
      if (monitor && Hyprland.monitorFor) {
        var screens = Quickshell.screens
        for (var i = 0; i < screens.length; i++) {
          var match = Hyprland.monitorFor(screens[i])
          if (match && monitor.name && match.name === monitor.name) return screens[i]
        }
      }
      return Quickshell.screens.length ? Quickshell.screens[0] : null
    }
  }
}
