.pragma library

// Row and frame durations (ms) per pose.
var POSES = {
  idle:    { row: 0, durations: [280, 110, 110, 140, 140, 320] },
  waving:  { row: 3, durations: [140, 140, 140, 280] },
  jumping: { row: 4, durations: [140, 140, 140, 140, 280] },
  waiting: { row: 6, durations: [150, 150, 150, 150, 150, 260] },
  running: { row: 7, durations: [120, 120, 120, 120, 120, 220] }
}

// Random behaviour pool, played ACTION_LOOPS times.
var ACTIONS = ["waving", "jumping", "waiting", "running"]
var ACTION_LOOPS = 2

function pickAction(previous, random) {
  var pool = ACTIONS.filter(function(name) { return name !== previous })
  return pool[Math.floor(random * pool.length)]
}

function drawWaitMs(random) {
  return 8000 + Math.floor(random * 12001)
}

// Rows 9-10: 16-way look wheel, index 0 = up, clockwise.
var LOOK_ROWS = 11
var NEUTRAL_FRAME = 6

function lookCell(dx, dy) {
  var index = Math.round(((Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360) / 22.5) % 16
  return { row: 9 + Math.floor(index / 8), frame: index % 8 }
}
