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
  property string dockMode: "always"
  property string dockEdge: "right"
  property bool dockPinned: false
  property bool doNotDisturb: false
  property bool omaboxActive: false
  property var lastArgs: []

  readonly property string home: Quickshell.env("HOME")
  readonly property string configPath: home + "/.config/omabox/services.toml"
  // __sourceDir is the absolute plugin checkout. The shell keeps it on the
  // manifest specifically so third-party plugins can find their own files.
  // Qt.resolvedUrl is the fallback before that injection, and for a Loader
  // whose document URL is Panel.qml.
  readonly property string cliPath: {
    var dir = manifest && manifest.__sourceDir ? String(manifest.__sourceDir) : ""
    if (dir.length > 0) return dir.replace(/\/$/, "") + "/bin/omabox"
    var url = Qt.resolvedUrl("bin/omabox").toString()
    if (url.indexOf("file://") === 0)
      url = decodeURIComponent(url.replace(/^file:\/\//, ""))
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
      if (data && (data.dock === "always" || data.dock === "special-only"))
        root.dockMode = data.dock
      if (data && (data.edge === "left" || data.edge === "right" || data.edge === "top" || data.edge === "bottom"))
        root.dockEdge = data.edge
      if (data && (data.pinned === true || data.pinned === false))
        root.dockPinned = data.pinned
      if (data && (data.dnd === true || data.dnd === false))
        root.doNotDisturb = data.dnd
    } catch (error) {
      console.warn("omabox: service list is not JSON")
    }
  }

  function syncWorkspace() {
    var names = []
    var ws = Hyprland.focusedWorkspace
    if (ws && ws.name) names.push(String(ws.name))
    var monitor = Hyprland.focusedMonitor
    var ipc = monitor && monitor.lastIpcObject ? monitor.lastIpcObject : null
    if (ipc && ipc.specialWorkspace && ipc.specialWorkspace.name)
      names.push(String(ipc.specialWorkspace.name))
    if (ipc && ipc.activeWorkspace && ipc.activeWorkspace.name)
      names.push(String(ipc.activeWorkspace.name))
    var active = false
    for (var i = 0; i < names.length; i++) {
      if (names[i] === "special:omabox" || names[i] === "omabox") active = true
    }
    root.omaboxActive = active
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
    syncWorkspace()
  }

  // Same Process path as `omabox list`, which is what fills the dock.
  // Util.execArgv goes through `bash -lc` and drops stderr, so a failed
  // launch looked like a click that did nothing.
  function run(args) {
    if (!root.cliPath) {
      console.warn("omabox: cli path is empty")
      return
    }
    if (launchProc.running) {
      console.warn("omabox: still launching; click again in a moment")
      return
    }
    root.lastArgs = args
    var argv = [root.cliPath]
    for (var i = 0; i < args.length; i++) argv.push(String(args[i]))
    launchProc.command = argv
    launchProc.running = true
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

  FileView {
    id: settingsFile
    path: root.home + "/.config/omabox/config.toml"
    watchChanges: true
    printErrors: false
    onLoaded: root.reloadServices()
    onFileChanged: reload()
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

  Process {
    id: launchProc
    stdout: StdioCollector {
      onStreamFinished: if (String(text || "").trim()) console.log("omabox: " + String(text).trim())
    }
    stderr: StdioCollector {
      onStreamFinished: if (String(text || "").trim()) console.warn("omabox: " + String(text).trim())
    }
    onExited: function(exitCode) {
      if (exitCode !== 0) console.warn("omabox: launch exited " + exitCode)
      if (root.lastArgs.length > 0 && (root.lastArgs[0] === "config" || root.lastArgs[0] === "service"))
        root.reloadServices()
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
    syncWorkspace()
  }

  // ShellIpc is a non-singleton type in qs.Commons. Quickshell exposes those
  // types only inside the shell config tree, so a third-party Panel.qml fails
  // with "ShellIpc is not a type" and never mounts (no dock, and
  // `omarchy-shell omabox dashboard` answers "Target not found.").
  // IpcHandler is Quickshell.Io. IpcRegistry is a Commons singleton, same as
  // Style, Util, and Color, which do resolve from a plugin directory.
  // shell/Commons/ShellIpc.qml is this same pair.
  IpcHandler {
    id: ipc
    target: "omabox"

    Component.onCompleted: Commons.IpcRegistry.register(ipc)
    Component.onDestruction: Commons.IpcRegistry.unregister(ipc)

    function dashboard(): string {
      root.open("{}")
      return "ok"
    }

    function reload(): string {
      root.reloadServices()
      return "ok"
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
}
