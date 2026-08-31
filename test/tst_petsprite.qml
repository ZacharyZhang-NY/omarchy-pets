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

  function test_action_plays_twice_then_idles_with_new_wait() {
    sprite.running = true
    verify(sprite.waitMs >= 8000 && sprite.waitMs <= 20000, "wait " + sprite.waitMs)
    var previous = ""
    for (var round = 0; round < 6; round++) {
      sprite.waitMs = 1
      tryVerify(function() { return sprite.pose !== "idle" }, 1000)
      var action = sprite.pose
      verify(["waving", "jumping", "waiting", "running"].indexOf(action) !== -1, action)
      verify(action !== previous, "repeated " + action)
      compare(sprite.loopsLeft, 2)
      tryCompare(sprite, "loopsLeft", 1, 2000)
      compare(sprite.pose, action)
      tryCompare(sprite, "pose", "idle", 2000)
      compare(sprite.frame, 0)
      verify(sprite.waitMs >= 8000 && sprite.waitMs <= 20000, "wait " + sprite.waitMs)
      previous = action
    }
    sprite.running = false
  }

  function test_random_behavior_off_stays_idle() {
    sprite.randomBehavior = false
    sprite.running = true
    sprite.waitMs = 1
    wait(1500)
    compare(sprite.pose, "idle")
    sprite.running = false
    sprite.randomBehavior = true
  }

  function test_toggling_random_behavior_resets_to_idle() {
    sprite.running = true
    sprite.waitMs = 1
    tryVerify(function() { return sprite.pose !== "idle" }, 1000)
    sprite.randomBehavior = false
    compare(sprite.pose, "idle")
    compare(sprite.frame, 0)
    verify(sprite.waitMs >= 8000 && sprite.waitMs <= 20000, "wait " + sprite.waitMs)
    sprite.waitMs = 1
    wait(600)
    compare(sprite.pose, "idle")
    tryCompare(sprite, "frame", 5, 2000)
    tryCompare(sprite, "frame", 0, 1000)
    wait(150)
    var toggledAt = Date.now()
    sprite.randomBehavior = true
    compare(sprite.pose, "idle")
    compare(sprite.frame, 0)
    verify(sprite.waitMs >= 8000 && sprite.waitMs <= 20000, "wait " + sprite.waitMs)
    var nextFrameAt = 0
    function stamp() { if (!nextFrameAt) nextFrameAt = Date.now() }
    sprite.frameChanged.connect(stamp)
    tryVerify(function() { return nextFrameAt > 0 }, 1000)
    sprite.frameChanged.disconnect(stamp)
    verify(nextFrameAt - toggledAt >= 250, "first frame " + (nextFrameAt - toggledAt) + " ms after toggle, expected a full 280 ms")
    sprite.running = false
  }
}
