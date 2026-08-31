pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "raiden-meixelysia.omarchy-pets"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null

  readonly property string home: Quickshell.env("HOME")
  readonly property string petsDir: {
    var raw = String(root.setting("petsDir", "~/.codex/pets"))
    return raw === "~" || raw.indexOf("~/") === 0 ? home + raw.slice(1) : raw
  }
  readonly property string petId: String(root.setting("petId", ""))
  readonly property bool smoothScaling: root.setting("smooth", true) === true
  readonly property bool animate: root.setting("animate", true) === true
  readonly property bool randomBehavior: root.setting("randomBehavior", true) === true
  readonly property bool pinned: root.setting("pinned", false) === true
  readonly property var currentPet: {
    var pets = library.pets
    for (var i = 0; i < pets.length; i++) if (pets[i].name === petId) return pets[i]
    return pets.length > 0 ? pets[0] : null
  }
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property color hoverFill: Style.hoverFillFor(barForeground, Color.accent)
  readonly property color selectedFill: Style.selectedFillFor(barForeground, Color.accent)

  // Where the stage sits inside the panel card, in screen coordinates.
  readonly property real cardInnerWidth: panel.contentWidth - Border.left(panel.borderSpec) - Border.right(panel.borderSpec) - panel.padding * 2
  readonly property int stageScreenX: Math.round(panel.cardOrigin.x + Border.left(panel.borderSpec) + panel.padding + (cardInnerWidth - stage.width) / 2)
  readonly property int stageScreenY: Math.round(panel.cardOrigin.y + Border.top(panel.borderSpec) + panel.padding)

  onOpenedChanged: if (opened) library.rescan()
  onPinnedChanged: if (pinned) root.controller.hide()

  function open() {
    if (pinned) saveSetting("pinned", false)
    root.controller.show()
  }

  function toggle() {
    if (pinned || !opened) open()
    else close()
  }

  function saveSetting(key, value) {
    var registry = bar && bar.shell ? bar.shell.pluginRegistry : null
    if (!registry) {
      console.warn("omarchy-pets: cannot save " + key + ": plugin registry unavailable")
      return
    }
    var error = registry.setBarWidget(moduleName, key, value, {})
    if (error) console.warn("omarchy-pets: saving " + key + " failed: " + error)
    else console.log("omarchy-pets: " + key + " = " + JSON.stringify(value))
  }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.hostWidget || root, direction)
    return false
  }

  PetLibrary {
    id: library
    active: root.hostWidget !== null
    petsDir: root.petsDir
  }

  // The pet and its pin button live in the panel card or in the pinned window.
  Item {
    id: stage
    parent: root.pinned ? pinnedSlot : panelSlot
    width: 192
    height: 208

    PetSprite {
      anchors.fill: parent
      sheetUrl: root.currentPet ? root.currentPet.sheetUrl : ""
      smoothScaling: root.smoothScaling
      running: (root.opened || root.pinned) && root.animate && root.currentPet !== null
      randomBehavior: root.randomBehavior
    }

    PanelActionButton {
      anchors.top: parent.top
      anchors.right: parent.right
      iconText: root.pinned ? "\u{f0930}" : "\u{f0403}"
      tooltipText: root.pinned ? "Unpin" : "Pin to the desktop"
      foreground: root.barForeground
      fontFamily: root.fontFamily
      onClicked: root.saveSetting("pinned", !root.pinned)
    }
  }

  PanelWindow {
    id: pinnedWindow
    visible: root.pinned && root.currentPet !== null
    screen: panel.screen
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "omarchy-pets"
    WlrLayershell.layer: WlrLayer.Top
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    anchors {
      left: true
      top: true
    }
    margins {
      left: root.stageScreenX
      top: root.stageScreenY
    }
    implicitWidth: stage.width
    implicitHeight: stage.height
    mask: Region { item: pinnedSlot }

    Item {
      id: pinnedSlot
      anchors.fill: parent
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(320))
    contentHeight: panel.fittedContentHeight(content.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: content
        width: parent.width
        spacing: Style.space(10)

        Item {
          id: panelSlot
          visible: root.currentPet !== null
          anchors.horizontalCenter: parent.horizontalCenter
          width: stage.width
          height: stage.height
        }

        Text {
          width: parent.width
          text: root.currentPet ? root.currentPet.displayName : "Pets"
          color: root.barForeground
          font.family: root.fontFamily
          font.pixelSize: Style.font.subtitle
          font.bold: true
          elide: Text.ElideRight
        }

        Text {
          visible: library.pets.length === 0
          width: parent.width
          text: "No pets in " + root.petsDir + "\nDownload one from codex-pets.net and unzip it into " + root.petsDir + "/<id>/"
          color: Qt.darker(root.barForeground, 1.5)
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.WrapAnywhere
        }

        ListView {
          visible: library.pets.length > 0
          width: parent.width
          height: Math.min(contentHeight, Style.space(320))
          spacing: Style.space(4)
          clip: true
          boundsBehavior: Flickable.StopAtBounds
          interactive: contentHeight > height
          model: library.pets

          ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

          delegate: PetRow {
            required property var modelData
            width: ListView.view.width
            pet: modelData
            current: root.currentPet !== null && root.currentPet.name === modelData.name
            foreground: root.barForeground
            fontFamily: root.fontFamily
            smoothScaling: root.smoothScaling
            fill: root.hoverFill
            currentFill: root.selectedFill
            onClicked: root.saveSetting("petId", modelData.name)
          }
        }
      }
    }
  }
}
