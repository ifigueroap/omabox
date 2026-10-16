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
    serviceMenuItems: serviceMenuItems
  }
}
