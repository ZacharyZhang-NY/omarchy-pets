import QtQuick
import QtTest
import "../Sprite.js" as Sprite

TestCase {
  name: "Sprite"

  function test_rows() {
    compare(Sprite.POSES.idle.row, 0)
    compare(Sprite.POSES.waving.row, 3)
    compare(Sprite.POSES.jumping.row, 4)
    compare(Sprite.POSES.waiting.row, 6)
    compare(Sprite.POSES.running.row, 7)
  }

  function test_frame_counts() {
    compare(Sprite.POSES.idle.durations.length, 6)
    compare(Sprite.POSES.waving.durations.length, 4)
    compare(Sprite.POSES.jumping.durations.length, 5)
    compare(Sprite.POSES.waiting.durations.length, 6)
    compare(Sprite.POSES.running.durations.length, 6)
  }

  function test_idle_blink() {
    var d = Sprite.POSES.idle.durations
    compare(d[1], 110)
    compare(d[2], 110)
    verify(d[1] < d[0] && d[2] < d[3])
  }

  function test_last_frame_held_longest() {
    for (var name in Sprite.POSES) {
      var d = Sprite.POSES[name].durations
      var last = d[d.length - 1]
      for (var i = 0; i < d.length - 1; i++) verify(d[i] < last, name + " frame " + i)
    }
  }

  function test_pick_action_never_repeats() {
    for (var p = 0; p < Sprite.ACTIONS.length; p++) {
      var previous = Sprite.ACTIONS[p]
      var seen = {}
      for (var r = 0; r < 1; r += 0.05) {
        var picked = Sprite.pickAction(previous, r)
        verify(picked !== previous, "picked " + picked + " after " + previous)
        verify(Sprite.ACTIONS.indexOf(picked) !== -1, picked)
        seen[picked] = true
      }
      compare(Object.keys(seen).length, Sprite.ACTIONS.length - 1)
    }
  }

  function test_first_pick_covers_whole_pool() {
    var seen = {}
    for (var r = 0; r < 1; r += 0.05) seen[Sprite.pickAction("", r)] = true
    compare(Object.keys(seen).length, Sprite.ACTIONS.length)
  }

  function test_wait_range() {
    compare(Sprite.drawWaitMs(0), 8000)
    compare(Sprite.drawWaitMs(0.999999), 20000)
    verify(Sprite.drawWaitMs(0.5) >= 8000 && Sprite.drawWaitMs(0.5) <= 20000)
  }
}
