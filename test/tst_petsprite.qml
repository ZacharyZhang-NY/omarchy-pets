import QtQuick
import QtTest
import ".."
import "../Sprite.js" as Sprite

TestCase {
  name: "PetSprite"

  PetSprite { id: sprite }

  function init() {
    sprite.running = false
    sprite.hovering = false
    sprite.randomBehavior = true
  }

  function loadAtlas(name) {
    sprite.sheetUrl = Qt.resolvedUrl(name)
    tryCompare(sprite, "ready", true, 3000)
  }

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

  function test_hover_looks_at_pointer_and_pauses_the_loop() {
    loadAtlas("atlas-v2.png")
    compare(sprite.lookEnabled, true)
    sprite.running = true
    var remaining = sprite.waitMs
    sprite.look = Sprite.lookCell(0, -100)
    sprite.hovering = true
    compare(sprite.looking, true)
    compare(sprite.cell, { row: 9, frame: 0 })
    sprite.look = Sprite.lookCell(100, 0)
    compare(sprite.cell, { row: 9, frame: 4 })
    wait(500)
    compare(sprite.waitMs, remaining)
    sprite.leave()
    compare(sprite.looking, false)
    compare(sprite.cell, { row: 0, frame: 6 })
    tryCompare(sprite, "neutralBeat", false, 1000)
    compare(sprite.pose, "idle")
    compare(sprite.cell.row, 0)
    tryVerify(function() { return sprite.waitMs < remaining }, 1000)
    sprite.running = false
  }

  function test_v1_atlas_ignores_hover() {
    loadAtlas("atlas-v1.png")
    compare(sprite.rows, 9)
    compare(sprite.lookEnabled, false)
    sprite.running = true
    sprite.hovering = true
    compare(sprite.looking, false)
    compare(sprite.cell.row, 0)
    sprite.leave()
    compare(sprite.neutralBeat, false)
    sprite.running = false
  }

  function test_wave_plays_once_then_idles_with_new_wait() {
    loadAtlas("atlas-v2.png")
    sprite.running = true
    sprite.wave()
    compare(sprite.pose, "waving")
    compare(sprite.loopsLeft, 1)
    tryCompare(sprite, "pose", "idle", 2000)
    verify(sprite.waitMs >= 8000 && sprite.waitMs <= 20000, "wait " + sprite.waitMs)
    sprite.running = false
  }

  function test_wave_while_hovering_then_returns_to_look() {
    loadAtlas("atlas-v2.png")
    sprite.running = true
    sprite.look = Sprite.lookCell(0, -100)
    sprite.hovering = true
    compare(sprite.looking, true)
    sprite.wave()
    compare(sprite.looking, false)
    compare(sprite.pose, "waving")
    tryCompare(sprite, "pose", "idle", 2000)
    compare(sprite.looking, true)
    compare(sprite.cell, { row: 9, frame: 0 })
    var remaining = sprite.waitMs
    wait(500)
    compare(sprite.waitMs, remaining)
    sprite.running = false
    sprite.leave()
    var frames = 0
    function count() { frames++ }
    sprite.frameChanged.connect(count)
    wait(700)
    sprite.frameChanged.disconnect(count)
    compare(frames, 0)
    compare(sprite.waitMs, remaining)
  }

  function test_hover_ignored_while_not_running() {
    loadAtlas("atlas-v2.png")
    compare(sprite.running, false)
    sprite.look = Sprite.lookCell(0, -100)
    sprite.hovering = true
    compare(sprite.looking, false)
    compare(sprite.cell, { row: 0, frame: 0 })
    sprite.leave()
    compare(sprite.neutralBeat, false)
    compare(sprite.cell, { row: 0, frame: 0 })
  }

  function test_neutral_beat_does_not_survive_a_v1_sheet() {
    loadAtlas("atlas-v2.png")
    sprite.running = true
    sprite.hovering = true
    sprite.leave()
    compare(sprite.cell, { row: 0, frame: 6 })
    loadAtlas("atlas-v1.png")
    compare(sprite.neutralBeat, false)
    compare(sprite.cell, { row: 0, frame: 0 })
    sprite.running = false
  }

  function test_wave_from_a_late_idle_frame_while_hovering_is_clean() {
    failOnWarning(/Cannot assign/)
    loadAtlas("atlas-v2.png")
    sprite.running = true
    tryCompare(sprite, "frame", 5, 2000)
    sprite.hovering = true
    compare(sprite.looking, true)
    sprite.wave()
    compare(sprite.pose, "waving")
    compare(sprite.frame, 0)
    tryCompare(sprite, "frame", 1, 500)
    tryCompare(sprite, "pose", "idle", 2000)
    sprite.leave()
    sprite.running = false
  }

  function test_wave_does_nothing_while_stopped() {
    loadAtlas("atlas-v2.png")
    compare(sprite.running, false)
    sprite.wave()
    compare(sprite.pose, "idle")
  }
}
