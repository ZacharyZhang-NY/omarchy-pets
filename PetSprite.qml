import QtQuick
import "Sprite.js" as Sprite

// One 192x208 cell of a Codex Pets atlas, animated by a single per-frame timer.
Item {
  id: root

  property url sheetUrl
  property bool smoothScaling: true
  property bool running: false
  property bool randomBehavior: true
  property string pose: "idle"
  property int frame: 0
  property int waitMs: 0
  property int loopsLeft: 0
  property string lastAction: ""

  readonly property bool ready: sheet.status === Image.Ready
  readonly property int rows: ready ? sheet.sourceSize.height / 208 : 0
  readonly property var durations: Sprite.POSES[pose].durations
  property url loggedSheet

  implicitWidth: 192
  implicitHeight: 208
  clip: true

  function restart() {
    beginIdle()
    arm()
  }

  function stop() {
    clock.stop()
    pose = "idle"
    frame = 0
  }

  function arm() {
    clock.interval = durations[frame]
    clock.restart()
  }

  function beginIdle() {
    pose = "idle"
    frame = 0
    waitMs = Sprite.drawWaitMs(Math.random())
  }

  function beginAction(name, loops) {
    pose = name
    lastAction = name
    loopsLeft = loops
    frame = 0
  }

  function step() {
    var elapsed = clock.interval
    frame = (frame + 1) % durations.length
    if (pose !== "idle") {
      if (frame === 0 && --loopsLeft === 0) beginIdle()
    } else {
      waitMs -= elapsed
      if (randomBehavior && waitMs <= 0) beginAction(Sprite.pickAction(lastAction, Math.random()), Sprite.ACTION_LOOPS)
    }
    arm()
  }

  onRunningChanged: {
    console.log("omarchy-pets: animation " + (running ? "started" : "stopped"))
    if (running) restart()
    else stop()
  }

  onRandomBehaviorChanged: if (running) restart()

  Timer {
    id: clock
    repeat: false
    onTriggered: root.step()
  }

  Image {
    id: sheet
    source: root.sheetUrl
    x: -root.frame * 192
    y: -Sprite.POSES[root.pose].row * 208
    smooth: root.smoothScaling
    asynchronous: true
    onStatusChanged: {
      if (status === Image.Error) console.warn("omarchy-pets: failed to load " + source)
      if (status !== Image.Ready || source === root.loggedSheet) return
      root.loggedSheet = source
      if (sourceSize.width !== 1536 || sourceSize.height % 208 !== 0)
        console.warn("omarchy-pets: unexpected atlas size " + sourceSize.width + "x" + sourceSize.height + " for " + source)
      console.log("omarchy-pets: loaded " + source + " rows=" + sourceSize.height / 208)
    }
  }
}
