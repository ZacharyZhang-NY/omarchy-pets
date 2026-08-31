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
}
