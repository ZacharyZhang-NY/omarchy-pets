import QtQuick
import Quickshell.Io

// Enumerates <petsDir>/*/; each pet carries its verified sheet inline.
QtObject {
  id: root

  property string petsDir: ""
  property bool active: false
  property var pets: []
  property string petsKey: ""
  property var collected: []
  property string scanDir: ""
  property bool rescanPending: false

  // One line per entry: "pet\t<dir>\t<json>" or "skip\t<dir>\t<reason>".
  readonly property string scanner: String(Qt.resolvedUrl("scan.py")).replace(/^file:\/\//, "")
  readonly property int scanTimeoutSec: 10

  function rescan() {
    if (!active) return
    if (scan.running) {
      rescanPending = true
      return
    }
    scanDir = petsDir
    collected = []
    scan.command = ["timeout", "-k", "2", String(scanTimeoutSec), "python3", scanner, scanDir]
    scan.running = true
  }

  function collect(line) {
    if (!line) return
    var parts = String(line).split("\t")
    if (parts[0] === "skip") {
      console.warn("omarchy-pets: skipped " + parts[1] + ": " + parts[2])
      return
    }
    if (parts[0] !== "pet") throw new Error("omarchy-pets: unexpected scan line: " + String(line).slice(0, 120))
    var dir = parts[1]
    var meta = JSON.parse(parts[2])
    if (typeof meta.sheet !== "string" || meta.sheet.indexOf("data:image/") !== 0 || typeof meta.digest !== "string")
      throw new Error("omarchy-pets: scan line without an inline sheet for " + dir)
    collected.push({
      name: dir.slice(dir.lastIndexOf("/") + 1),
      displayName: meta.displayName || meta.id,
      kind: meta.kind || "",
      digest: meta.digest,
      sheetUrl: meta.sheet
    })
  }

  function apply(next) {
    // Compared without the sheets: serialising them costs hundreds of MB.
    var key = next.map(function(pet) { return [pet.name, pet.displayName, pet.kind, pet.digest].join("\t") }).join("\n")
    if (key === petsKey) return
    petsKey = key
    pets = next
    var names = next.map(function(pet) { return pet.name }).join(", ")
    console.log("omarchy-pets: " + next.length + " pet(s) in " + petsDir + (names ? ": " + names : ""))
  }

  property Process scan: Process {
    stdout: SplitParser { onRead: function(line) { root.collect(line) } }
    stderr: StdioCollector { id: scanErr; waitForEnd: true }
    onExited: function(code, status) {
      if (scanErr.text) console.warn("omarchy-pets: scan stderr: " + scanErr.text.trim())
      if (code === 124) console.warn("omarchy-pets: scan of " + root.scanDir + " timed out after " + root.scanTimeoutSec + " s")
      else if (code !== 0) console.warn("omarchy-pets: scan of " + root.scanDir + " exited with " + code)
      else if (root.scanDir === root.petsDir) root.apply(root.collected)
      root.collected = []
      if (root.rescanPending) {
        root.rescanPending = false
        root.rescan()
      }
    }
  }

  onActiveChanged: rescan()
  onPetsDirChanged: rescan()
}
