import QtQuick
import QtTest
import "../Settings.js" as Settings

TestCase {
  name: "Settings"

  readonly property string pluginId: "raiden-meixelysia.omarchy-pets"

  // The shell builds its facade with createObject initial properties, which turn arrays into Qt sequences.
  Component {
    id: facade
    QtObject { property var barConfig }
  }

  function barConfig(right) {
    return { position: "top", layout: { left: ["omarchy"], center: ["clock"], right: right } }
  }

  function test_stored_entry_wins_over_the_injected_copy() {
    var stale = { petId: "guga", pinned: false, pinnedX: 10 }
    var config = barConfig(["tray", { id: pluginId, petId: "remiel", pinned: true, pinnedX: 34 }])
    compare(Settings.current(config, pluginId, stale), { petId: "remiel", pinned: true, pinnedX: 34 })
  }

  function test_entry_found_in_any_region() {
    var config = { layout: { left: [{ id: "other", smooth: true }, { id: pluginId, smooth: false }], center: [], right: [] } }
    compare(Settings.current(config, pluginId, { smooth: true }), { smooth: false })
  }

  function test_entry_found_in_a_facade_built_config() {
    var built = facade.createObject(null, { barConfig: barConfig(["tray", { id: pluginId, pinned: true }]) })
    verify(!Array.isArray(built.barConfig.layout.right))
    compare(Settings.current(built.barConfig, pluginId, { pinned: false }), { pinned: true })
    built.destroy()
  }

  function test_string_entry_has_no_settings() {
    compare(Settings.current(barConfig([pluginId]), pluginId, { pinned: false }), {})
  }

  function test_injected_copy_when_the_config_lacks_the_entry() {
    var injected = { pinned: false }
    compare(Settings.current(barConfig(["tray"]), pluginId, injected), injected)
    compare(Settings.current({ position: "top" }, pluginId, injected), injected)
    compare(Settings.current(null, pluginId, injected), injected)
  }
}
