import QtQuick

// One 192x208 cell of a Codex Pets atlas, picked by row/frame offsets.
Item {
  id: root

  property url sheetUrl
  property bool smoothScaling: true
  property int row: 0
  property int frame: 0

  readonly property bool ready: sheet.status === Image.Ready
  readonly property int rows: ready ? sheet.sourceSize.height / 208 : 0
  property url loggedSheet

  implicitWidth: 192
  implicitHeight: 208
  clip: true

  Image {
    id: sheet
    source: root.sheetUrl
    x: -root.frame * 192
    y: -root.row * 208
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
}
