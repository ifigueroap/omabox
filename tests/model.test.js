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

console.log("model.test.js ok")
