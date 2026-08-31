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
  property bool hovering: false
  property var look: ({ row: 0, frame: 0 })
  property bool neutralBeat: false

  readonly property bool ready: sheet.status === Image.Ready
  readonly property int rows: ready ? sheet.sourceSize.height / 208 : 0
  readonly property bool lookEnabled: rows >= Sprite.LOOK_ROWS
  readonly property bool looking: running && lookEnabled && hovering && pose === "idle"
  readonly property bool ticking: running && !looking
  readonly property var durations: Sprite.POSES[pose].durations
  readonly property var cell: looking ? look
    : (neutralBeat ? { row: 0, frame: Sprite.NEUTRAL_FRAME } : { row: Sprite.POSES[pose].row, frame: frame })
  property url loggedSheet

  implicitWidth: 192
  implicitHeight: 208
  clip: true

  function restart() {
    beginIdle()
    if (ticking) arm()
  }

  function arm() {
    clock.interval = durations[frame]
    clock.restart()
  }

  function beginIdle() {
    frame = 0
    neutralBeat = false
    pose = "idle"
    waitMs = Sprite.drawWaitMs(Math.random())
  }

  function beginAction(name, loops) {
    frame = 0
    neutralBeat = false
    lastAction = name
    loopsLeft = loops
    pose = name
  }

  function wave() {
    if (!running) return
    beginAction("waving", 1)
    if (ticking) arm()
  }

  function leave() {
    if (looking) {
      frame = 0
      neutralBeat = true
    }
    hovering = false
  }

  function step() {
    if (neutralBeat) {
      neutralBeat = false
      arm()
      return
    }
    var elapsed = clock.interval
    frame = (frame + 1) % durations.length
    if (pose !== "idle") {
      if (frame === 0 && --loopsLeft === 0) beginIdle()
    } else {
      waitMs -= elapsed
      if (randomBehavior && waitMs <= 0) beginAction(Sprite.pickAction(lastAction, Math.random()), Sprite.ACTION_LOOPS)
    }
    if (ticking) arm()
  }

  onRunningChanged: {
    console.log("omarchy-pets: animation " + (running ? "started" : "stopped"))
    if (running) beginIdle()
    else {
      clock.stop()
      pose = "idle"
      frame = 0
      neutralBeat = false
    }
  }

  onTickingChanged: {
    if (ticking) arm()
    else clock.stop()
  }

  onRandomBehaviorChanged: if (running) restart()
  onLookEnabledChanged: if (!lookEnabled) neutralBeat = false

  Timer {
    id: clock
    repeat: false
    onTriggered: root.step()
  }

  Image {
    id: sheet
    source: root.sheetUrl
    x: -root.cell.frame * 192
    y: -root.cell.row * 208
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

  MouseArea {
    id: mouse
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onEntered: {
      root.look = Sprite.lookCell(mouseX - width / 2, mouseY - height / 2)
      root.hovering = true
    }
    onPositionChanged: function(event) { root.look = Sprite.lookCell(event.x - width / 2, event.y - height / 2) }
    onExited: root.leave()
    onClicked: root.wave()
  }
}
