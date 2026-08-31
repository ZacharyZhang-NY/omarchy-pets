import QtQuick
import Quickshell.Io
import qs.Commons

// Enumerates <petsDir>/*/ and keeps the valid Codex Pets.
QtObject {
  id: root

  property string petsDir: ""
  property bool active: false
  property var pets: []
  property string scanDir: ""
  property bool rescanPending: false

  // One line per entry: "pet\t<dir>\t<json>" or "skip\t<dir>\t<reason>".
  readonly property string scanScript: `
dir="$1"
[[ -d "$dir" ]] || exit 0
skip() { printf 'skip\\t%s\\t%s\\n' "$sub" "$1"; }
validate='
  if length != 1 or (.[0] | type) != "object" then "pet.json is not a single JSON object"
  elif (.[0].id | type) != "string" or .[0].id == "" then "pet.json has no id"
  elif (.[0].spritesheetPath | type) != "string" or .[0].spritesheetPath == ""
       or (.[0].spritesheetPath | explode | any(. < 32))
       or (.[0].spritesheetPath | startswith("/") or contains("..")) then "spritesheetPath is not a plain relative path"
  else .[0] | {id, displayName, kind, spritesheetPath} end'
shopt -s dotglob
for sub in "$dir"/*; do
  [[ -f "$sub/pet.json" ]] || continue
  [[ $sub == *[$'\\t\\n']* ]] && continue
  meta=$(jq -c --slurp "$validate" "$sub/pet.json" 2>/dev/null) || { skip "pet.json is not valid JSON"; continue; }
  [[ $meta == \\{* ]] || { skip "\${meta:1:-1}"; continue; }
  sheet=$(jq -r .spritesheetPath <<<"$meta")
  [[ -f "$sub/$sheet" ]] || { skip "spritesheet missing: $sheet"; continue; }
  height=$(identify -format '%h' "$sub/$sheet[0]" 2>/dev/null) || { skip "unreadable spritesheet"; continue; }
  (( height % 208 == 0 )) || { skip "atlas height $height is not a multiple of 208"; continue; }
  printf 'pet\\t%s\\t%s\\n' "$sub" "$meta"
done
`

  function rescan() {
    if (!active) return
    if (scan.running) {
      rescanPending = true
      return
    }
    scanDir = petsDir
    scan.command = ["bash", "-c", scanScript, "omarchy-pets-scan", scanDir]
    scan.running = true
  }

  function apply(output) {
    var next = []
    var lines = output.split("\n")
    for (var i = 0; i < lines.length; i++) {
      if (!lines[i]) continue
      var parts = lines[i].split("\t")
      if (parts[0] === "skip") {
        console.warn("omarchy-pets: skipped " + parts[1] + ": " + parts[2])
        continue
      }
      if (parts[0] !== "pet") throw new Error("omarchy-pets: unexpected scan line: " + lines[i])
      var dir = parts[1]
      var meta = JSON.parse(parts[2])
      next.push({
        name: dir.slice(dir.lastIndexOf("/") + 1),
        displayName: meta.displayName || meta.id,
        kind: meta.kind || "",
        sheetUrl: Util.fileUrl(dir + "/" + meta.spritesheetPath)
      })
    }
    if (JSON.stringify(next) === JSON.stringify(pets)) return
    pets = next
    var names = next.map(function(pet) { return pet.name }).join(", ")
    console.log("omarchy-pets: " + next.length + " pet(s) in " + petsDir + (names ? ": " + names : ""))
  }

  property Process scan: Process {
    stdout: StdioCollector { id: scanOut; waitForEnd: true }
    stderr: StdioCollector { id: scanErr; waitForEnd: true }
    onExited: function(code, status) {
      if (scanErr.text) console.warn("omarchy-pets: scan stderr: " + scanErr.text.trim())
      if (code !== 0) console.warn("omarchy-pets: scan of " + root.scanDir + " exited with " + code)
      else if (root.scanDir === root.petsDir) root.apply(scanOut.text)
      if (root.rescanPending) {
        root.rescanPending = false
        root.rescan()
      }
    }
  }

  onActiveChanged: rescan()
  onPetsDirChanged: rescan()
}
