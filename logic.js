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

// Hyprland windowtitlev2 payload is "ADDRESS,title" and the title may contain commas.
function eventTitle(data) {
  var text = String(data || "")
  var comma = text.indexOf(",")
  if (comma < 0) return { address: normAddress(text), title: "" }
  return { address: normAddress(text.slice(0, comma)), title: text.slice(comma + 1) }
}

if (typeof module === "object" && module.exports) {
  module.exports = {
    parseHttpUrl: parseHttpUrl,
    windowClass: windowClass,
    unreadCount: unreadCount,
    normAddress: normAddress,
    eventTitle: eventTitle
  }
}
