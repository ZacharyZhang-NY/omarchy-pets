.pragma library

// Row and per-frame durations (ms) of each pose this plugin plays.
var POSES = {
  idle:    { row: 0, durations: [280, 110, 110, 140, 140, 320] },
  waving:  { row: 3, durations: [140, 140, 140, 280] },
  jumping: { row: 4, durations: [140, 140, 140, 140, 280] },
  waiting: { row: 6, durations: [150, 150, 150, 150, 150, 260] },
  running: { row: 7, durations: [120, 120, 120, 120, 120, 220] }
}
