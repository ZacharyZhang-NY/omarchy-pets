import QtQuick
import QtTest
import ".."

TestCase {
  name: "PetSprite"

  PetSprite { id: sprite }

  function test_stopped_holds_idle_frame_zero() {
    compare(sprite.running, false)
    wait(400)
    compare(sprite.pose, "idle")
    compare(sprite.frame, 0)
  }

  function test_frames_follow_idle_durations() {
    var stamps = []
    function record() { stamps.push({ frame: sprite.frame, at: Date.now() }) }
    sprite.frameChanged.connect(record)
    var previous = Date.now()
    sprite.running = true
    tryVerify(function() { return stamps.length >= 6 }, 3000)
    sprite.running = false
    sprite.frameChanged.disconnect(record)

    var expected = [280, 110, 110, 140, 140, 320]
    for (var i = 0; i < 6; i++) {
      compare(stamps[i].frame, (i + 1) % 6)
      var elapsed = stamps[i].at - previous
      verify(Math.abs(elapsed - expected[i]) < 60, "frame " + stamps[i].frame + " after " + elapsed + " ms, expected " + expected[i])
      previous = stamps[i].at
    }
    compare(sprite.frame, 0)
  }
}
