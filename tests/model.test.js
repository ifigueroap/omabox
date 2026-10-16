const assert = require("assert")
const fs = require("fs")
const path = require("path")
const Logic = require("../logic.js")

const rows = fs.readFileSync(path.join(__dirname, "classes.tsv"), "utf8")
  .trim()
  .split("\n")
  .map((line) => line.split("\t"))

for (const [url, profile, expected] of rows) {
  assert.strictEqual(Logic.windowClass(url, profile), expected, url)
}

assert.strictEqual(Logic.windowClass("", "WhatsApp"), "")
assert.strictEqual(Logic.windowClass("https://web.whatsapp.com/", ""), "")
assert.strictEqual(Logic.windowClass("file:///tmp/x", "WhatsApp"), "")

assert.strictEqual(Logic.unreadCount("(3) WhatsApp", "^\\((\\d+)\\)"), 3)
assert.strictEqual(Logic.unreadCount("(12) Slack", "^\\((\\d+)\\)"), 12)
assert.strictEqual(Logic.unreadCount("WhatsApp", "^\\((\\d+)\\)"), 0)
assert.strictEqual(Logic.unreadCount("(0) WhatsApp", "^\\((\\d+)\\)"), 0)
assert.strictEqual(Logic.unreadCount("3 WhatsApp", "^\\((\\d+)\\)"), 0)
assert.strictEqual(Logic.unreadCount("(3) (9) x", "^\\((\\d+)\\)"), 3)
assert.strictEqual(Logic.unreadCount("(4) hi", "["), 0)
assert.strictEqual(Logic.unreadCount("", "^\\((\\d+)\\)"), 0)

const titled = Logic.eventTitle("0xabc,(3) Hello, world")
assert.strictEqual(titled.address, "0xabc")
assert.strictEqual(titled.title, "(3) Hello, world")
assert.strictEqual(Logic.unreadCount(titled.title, "^\\((\\d+)\\)"), 3)
assert.strictEqual(Logic.normAddress("ABC"), "0xabc")
assert.strictEqual(Logic.normAddress("0xABC"), "0xabc")

assert.strictEqual(Logic.dockPresentation("always", false, false), "notch")
assert.strictEqual(Logic.dockPresentation("always", false, true), "full")
assert.strictEqual(Logic.dockPresentation("always", true, false), "full")
assert.strictEqual(Logic.dockPresentation("special-only", false, true), "hidden")
assert.strictEqual(Logic.dockPresentation("special-only", true, false), "full")
assert.strictEqual(Logic.dockPresentation("other", false, false), "notch")
assert.strictEqual(Logic.dockPresentation("always", false, false, true), "full")
assert.strictEqual(Logic.dockPresentation("special-only", false, false, true), "hidden")
assert.strictEqual(Logic.dockPresentation("special-only", true, false, false), "full")
assert.ok(Logic.dockOpacity(false, false, false) < Logic.dockOpacity(true, false, false))
assert.strictEqual(Logic.dockOpacity(false, false, false), Logic.DOCK_IDLE_OPACITY)
assert.strictEqual(Logic.dockOpacity(true, false, false), 1)
assert.strictEqual(Logic.dockOpacity(false, true, false), 1)
assert.strictEqual(Logic.dockOpacity(false, false, true), 1)

assert.strictEqual(Logic.allowsSound({ sound: true }, false), true)
assert.strictEqual(Logic.allowsSound({ sound: false }, false), false)
assert.strictEqual(Logic.allowsSound({}, false), true)
assert.strictEqual(Logic.allowsSound({ sound: true }, true), false)
assert.strictEqual(Logic.allowsSound({ sound: true }, "true"), false)
assert.strictEqual(Logic.allowsBadges({ badges: false }, false), false)
assert.strictEqual(Logic.allowsBadges({ badges: true }, true), false)
assert.strictEqual(Logic.allowsBadges({}, false), true)
assert.strictEqual(Logic.allowsBadges(null, false), true)

const menuOn = Logic.serviceMenuItems({ sound: true, badges: true })
assert.strictEqual(menuOn.length, 2)
assert.strictEqual(menuOn[0].field, "sound")
assert.strictEqual(menuOn[0].label, "Sound")
assert.strictEqual(menuOn[0].enabled, true)
assert.strictEqual(menuOn[0].next, "false")
assert.strictEqual(menuOn[1].field, "badges")
assert.strictEqual(menuOn[1].label, "Badges")
assert.strictEqual(menuOn[1].next, "false")

const menuOff = Logic.serviceMenuItems({ sound: false, badges: false })
assert.strictEqual(menuOff[0].enabled, false)
assert.strictEqual(menuOff[0].next, "true")
assert.strictEqual(menuOff[1].enabled, false)
assert.strictEqual(menuOff[1].next, "true")
assert.strictEqual(Logic.serviceMenuItems(null)[0].enabled, true)
assert.strictEqual(Logic.serviceMenuItems({}).length, 2)

const whatsapp = { class: "chrome-web.whatsapp.com__-WhatsApp", unread: "^\\((\\d+)\\)" }
const slack = { class: "chrome-app.slack.com__-Slack", unread: "^\\((\\d+)\\)" }
const windows = {
  "0x1": { className: whatsapp.class, title: "(3) WhatsApp", urgent: false },
  "0x2": { className: whatsapp.class, title: "(1) WhatsApp", urgent: true },
  "0x3": { className: slack.class, title: "(2) Slack", urgent: false },
  "0x4": { className: slack.class, title: "Slack", urgent: true }
}
assert.strictEqual(Logic.serviceUnread(whatsapp, windows), 3)
assert.strictEqual(Logic.serviceUnread(slack, windows), 2)
assert.strictEqual(Logic.totalUnread([whatsapp, slack], windows), 5)
assert.strictEqual(Logic.totalUnread([whatsapp, slack], windows, true), 0)
assert.strictEqual(Logic.totalUnread([whatsapp, slack], windows, "true"), 0)
assert.strictEqual(Logic.totalUnread([Object.assign({}, whatsapp, { badges: false }), slack], windows, false), 2)
assert.strictEqual(Logic.totalUnread([whatsapp, slack], {}), 0)
assert.strictEqual(Logic.totalUnread([], windows), 0)
assert.strictEqual(Logic.totalUnread(null, null), 0)
assert.strictEqual(Logic.unreadLabel(0), "")
assert.strictEqual(Logic.unreadLabel(5), "5")
assert.strictEqual(Logic.unreadLabel(100), "99+")

let tracked = {}
tracked = Logic.handleWindowEvent(tracked, { name: "windowtitlev2", data: "0xabc,(4) WhatsApp" })
assert.strictEqual(tracked["0xabc"].title, "(4) WhatsApp")
assert.strictEqual(Logic.totalUnread([whatsapp], tracked), 0)
tracked["0xabc"].className = whatsapp.class
assert.strictEqual(Logic.totalUnread([whatsapp], tracked), 4)
tracked = Logic.handleWindowEvent(tracked, { name: "urgent", data: "0xABC" })
assert.strictEqual(tracked["0xabc"].urgent, true)
assert.strictEqual(tracked["0xabc"].title, "(4) WhatsApp")
tracked = Logic.handleWindowEvent(tracked, { name: "activewindowv2", data: "abc" })
assert.strictEqual(tracked["0xabc"].urgent, false)
tracked = Logic.handleWindowEvent(tracked, { name: "closewindow", data: "0xabc" })
assert.strictEqual(tracked["0xabc"], undefined)
assert.strictEqual(Logic.totalUnread([whatsapp], tracked), 0)

const keptUrgent = Logic.syncToplevels(
  { "0xabc": { className: "old", title: "(4) WhatsApp", urgent: true } },
  [{ lastIpcObject: { address: "0xABC", class: whatsapp.class, title: "" } }]
)
assert.strictEqual(keptUrgent["0xabc"].className, whatsapp.class)
assert.strictEqual(keptUrgent["0xabc"].title, "(4) WhatsApp")
assert.strictEqual(keptUrgent["0xabc"].urgent, true)
assert.strictEqual(Logic.totalUnread([whatsapp], keptUrgent), 4)
assert.strictEqual(Object.keys(Logic.syncToplevels(keptUrgent, [])).length, 1)
assert.strictEqual(Logic.handleWindowEvent(keptUrgent, { name: "openwindow" }), keptUrgent)

console.log("model.test.js ok")
