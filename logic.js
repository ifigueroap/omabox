// Shared by the dock (QML import) and tests/model.test.js (Node).
// Window class matches Chromium's Wayland app id for --app plus
// --profile-directory, which is the same formula as Omarchy's
// bin/omarchy-webapp-window-class with the profile basename in place of
// "Default":
//   app = host + "_" + path          (web_app::GenerateApplicationNameFromURL)
//   id  = "chrome-" + app + "-" + profile
//   then "/" and " " become "_"      (GetShortcutFileName)

function parseHttpUrl(url) {
  var raw = String(url || "").trim()
  var match = raw.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):\/\/([^?#]*)/)
  if (!match) return null
  if (match[1].toLowerCase() !== "http" && match[1].toLowerCase() !== "https") return null
  var address = match[2]
  var slash = address.indexOf("/")
  var host = slash === -1 ? address : address.slice(0, slash)
  var path = slash === -1 ? "/" : address.slice(slash)
  if (!path) path = "/"
  var at = host.lastIndexOf("@")
  if (at !== -1) host = host.slice(at + 1)
  if (host.charAt(0) === "[") {
    var end = host.indexOf("]")
    if (end !== -1) host = host.slice(0, end + 1)
  } else {
    var colon = host.indexOf(":")
    if (colon !== -1) host = host.slice(0, colon)
  }
  host = host.toLowerCase()
  if (!host) return null
  return { host: host, path: path }
}

function windowClass(url, profile) {
  var parsed = parseHttpUrl(url)
  var name = String(profile || "")
  if (!parsed || !name) return ""
  return ("chrome-" + parsed.host + "_" + parsed.path + "-" + name).replace(/\//g, "_").replace(/ /g, "_")
}

function unreadCount(title, pattern) {
  if (!title || !pattern) return 0
  var expression
  try {
    expression = new RegExp(pattern)
  } catch (error) {
    return 0
  }
  var match = String(title).match(expression)
  if (!match) return 0
  var value = parseInt(match[1] !== undefined ? match[1] : match[0], 10)
  return isFinite(value) && value > 0 ? value : 0
}

function normAddress(value) {
  var text = String(value || "").trim().toLowerCase()
  if (!text) return ""
  if (text.indexOf("0x") !== 0) text = "0x" + text
  return text
}

// Dock shape on screen. `latched` stays true briefly after the pointer leaves
// so the expanded dock does not collapse between the notch and an icon.
// `pinned` keeps the pill open. special-only still hides the dock off omabox.
function dockPresentation(mode, onOmabox, latched, pinned) {
  if (mode === "special-only" && !onOmabox) return "hidden"
  if (onOmabox || latched || pinned) return "full"
  return "notch"
}

// Idle notch (and the brief expanded tail after the pointer leaves) is faded.
// Hover, pin, and the omabox workspace use the theme colors at full strength.
var DOCK_IDLE_OPACITY = 0.35

function dockOpacity(pointerInside, pinned, onOmabox) {
  if (pointerInside || pinned || onOmabox) return 1
  return DOCK_IDLE_OPACITY
}

// Hyprland windowtitlev2 payload is "ADDRESS,title" and the title may contain commas.

function eventTitle(data) {
  var text = String(data || "")
  var comma = text.indexOf(",")
  if (comma < 0) return { address: normAddress(text), title: "" }
  return { address: normAddress(text.slice(0, comma)), title: text.slice(comma + 1) }
}

// Do not disturb overrides per-service sound and badges. A missing flag stays on
// so an older services list keeps making sound and showing badges.
function isDnd(dnd) {
  return dnd === true || dnd === "true" || dnd === 1
}

function flagEnabled(value) {
  return value !== false && value !== "false" && value !== 0
}

function allowsSound(service, dnd) {
  if (isDnd(dnd)) return false
  if (!service) return true
  return flagEnabled(service.sound)
}

function allowsBadges(service, dnd) {
  if (isDnd(dnd)) return false
  if (!service) return true
  return flagEnabled(service.badges)
}

function serviceMenuItems(service) {
  var sound = !service || flagEnabled(service.sound)
  var badges = !service || flagEnabled(service.badges)
  return [
    { field: "sound", label: "Sound", enabled: sound, next: sound ? "false" : "true" },
    { field: "badges", label: "Badges", enabled: badges, next: badges ? "false" : "true" }
  ]
}

// Same per-window count the dock badge uses: the highest parsed title count
// for that service's class. Several windows of one class do not add together.
function serviceUnread(service, windows) {
  if (!service) return 0
  var best = 0
  var rows = windows || {}
  for (var address in rows) {
    var row = rows[address]
    if (!row || row.className !== service.class) continue
    var count = unreadCount(row.title, service.unread)
    if (count > best) best = count
  }
  return best
}

// Sum of the dock's per-service title counts. Services with badges off, and
// every service while Do not disturb is on, contribute nothing. Zero hides
// the bar badge. An urgent dot with no parsed count is not added here.
function totalUnread(services, windows, dnd) {
  if (isDnd(dnd)) return 0
  var rows = services || []
  var total = 0
  for (var i = 0; i < rows.length; i++) {
    if (!allowsBadges(rows[i], dnd)) continue
    total += serviceUnread(rows[i], windows)
  }
  return total
}

function unreadLabel(total) {
  if (!total || total <= 0) return ""
  return total > 99 ? "99+" : String(total)
}

function copyWindows(windows) {
  var next = {}
  var rows = windows || {}
  for (var key in rows) next[key] = rows[key]
  return next
}

function mergeWindow(windows, address, patch) {
  var key = normAddress(address)
  if (!key) return copyWindows(windows)
  var next = copyWindows(windows)
  var prev = next[key] || { className: "", title: "", urgent: false }
  var incoming = patch || {}
  next[key] = {
    className: incoming.className !== undefined ? incoming.className : prev.className,
    title: incoming.title !== undefined ? incoming.title : prev.title,
    urgent: incoming.urgent !== undefined ? incoming.urgent : prev.urgent
  }
  return next
}

function forgetWindow(windows, address) {
  var key = normAddress(address)
  var next = {}
  var rows = windows || {}
  for (var existing in rows) {
    if (existing !== key) next[existing] = rows[existing]
  }
  return next
}

// Hyprland toplevel snapshot. An empty list keeps the previous map, matching
// the panel: a brief empty read must not clear badges.
function syncToplevels(windows, values) {
  var list = values || []
  var prevWindows = windows || {}
  var next = {}
  for (var i = 0; i < list.length; i++) {
    var top = list[i]
    if (!top) continue
    var ipc = top.lastIpcObject || {}
    var wayland = top.wayland || null
    var key = normAddress(ipc.address || top.address || "")
    if (!key) continue
    var prev = prevWindows[key] || null
    var wm = String(ipc.class || ipc.initialClass || (wayland && wayland.appId) || "")
    var title = String(ipc.title || ipc.initialTitle || "")
    next[key] = {
      className: wm || (prev ? prev.className : ""),
      title: title || (prev ? prev.title : ""),
      urgent: prev ? prev.urgent === true : false
    }
  }
  if (list.length === 0) {
    for (var kept in prevWindows) next[kept] = prevWindows[kept]
  }
  return next
}

// Title, urgent, focus, and close. openwindow / windowtitle still refresh
// from the toplevel list in QML, because that list is live Hyprland state.
function handleWindowEvent(windows, event) {
  var current = windows || {}
  if (!event || !event.name) return current
  var name = String(event.name)
  var data = event.data !== undefined && event.data !== null ? String(event.data) : ""
  if (name === "windowtitlev2") {
    var parsed = eventTitle(data)
    return mergeWindow(current, parsed.address, { title: parsed.title })
  }
  if (name === "urgent") return mergeWindow(current, data, { urgent: true })
  if (name === "activewindowv2") return mergeWindow(current, data, { urgent: false })
  if (name === "closewindow") return forgetWindow(current, data)
  return current
}

if (typeof module === "object" && module.exports) {
  module.exports = {
    parseHttpUrl: parseHttpUrl,
    windowClass: windowClass,
    unreadCount: unreadCount,
    normAddress: normAddress,
    dockPresentation: dockPresentation,
    dockOpacity: dockOpacity,
    DOCK_IDLE_OPACITY: DOCK_IDLE_OPACITY,
    eventTitle: eventTitle,
    isDnd: isDnd,
    allowsSound: allowsSound,
    allowsBadges: allowsBadges,
    serviceMenuItems: serviceMenuItems,
    serviceUnread: serviceUnread,
    totalUnread: totalUnread,
    unreadLabel: unreadLabel,
    mergeWindow: mergeWindow,
    forgetWindow: forgetWindow,
    syncToplevels: syncToplevels,
    handleWindowEvent: handleWindowEvent
  }
}
