import QtQuick
import "Sprite.js" as Sprite

// One atlas cell, animated by one per-frame timer.
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
  property real pressX: 0
  property real pressY: 0
  property bool dragMoved: false

  readonly property bool ready: sheet.status === Image.Ready
  readonly property int rows: ready ? sheet.sourceSize.height / 208 : 0
  readonly property bool lookEnabled: rows >= Sprite.LOOK_ROWS
  readonly property bool looking: running && lookEnabled && hovering && pose === "idle"
  readonly property bool ticking: running && !looking
  readonly property var durations: Sprite.POSES[pose].durations
  readonly property var cell: looking ? look
    : (neutralBeat ? { row: 0, frame: Sprite.NEUTRAL_FRAME } : { row: Sprite.POSES[pose].row, frame: frame })
  property url loggedSheet

  signal dragged(real dx, real dy)
  signal dropped()

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

  function press(x, y) {
    pressX = x
    pressY = y
    dragMoved = false
  }

  function drag(x, y) {
    var dx = x - pressX
    var dy = y - pressY
    if (!dragMoved && Math.hypot(dx, dy) < Application.styleHints.startDragDistance) return
    dragMoved = true
    dragged(dx, dy)
  }

  function release() {
    if (dragMoved) dropped()
    else wave()
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
    onPositionChanged: function(event) {
      root.look = Sprite.lookCell(event.x - width / 2, event.y - height / 2)
      if (pressed) root.drag(event.x, event.y)
    }
    onExited: root.leave()
    onPressed: function(event) { root.press(event.x, event.y) }
    onReleased: root.release()
  }
}
