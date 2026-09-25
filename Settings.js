.pragma library

// The bar re-injects a reloaded widget with the settings its slot was built with; the stored entry is current.
function current(barConfig, id, injected) {
  var layout = barConfig ? barConfig.layout : null
  if (!layout) return injected
  var regions = ["left", "center", "right"]
  for (var r = 0; r < regions.length; r++) {
    var entries = Array.isArray(layout[regions[r]]) ? layout[regions[r]] : []
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i]
      if (entry === id) return {}
      if (!entry || entry.id !== id) continue
      var settings = {}
      for (var key in entry) if (key !== "id") settings[key] = entry[key]
      return settings
    }
  }
  return injected
}
