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
  readonly property int pinnedX: root.setting("pinnedX", -1)
  readonly property int pinnedY: root.setting("pinnedY", -1)
  property int dragDx: 0
  property int dragDy: 0
  readonly property int previewCount: 3
  property bool showAll: false
  readonly property var currentPet: {
    var pets = library.pets
    for (var i = 0; i < pets.length; i++) if (pets[i].name === petId) return pets[i]
    return pets.length > 0 ? pets[0] : null
  }
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property color hoverFill: Style.hoverFillFor(barForeground, Color.accent)
  readonly property color selectedFill: Style.selectedFillFor(barForeground, Color.accent)

  // Stage position inside the card, screen coordinates.
  readonly property real cardInnerWidth: panel.contentWidth - Border.left(panel.borderSpec) - Border.right(panel.borderSpec) - panel.padding * 2
  readonly property int stageScreenX: Math.round(panel.cardOrigin.x + Border.left(panel.borderSpec) + panel.padding + (cardInnerWidth - stage.width) / 2)
  readonly property int stageScreenY: Math.round(panel.cardOrigin.y + Border.top(panel.borderSpec) + panel.padding)

  // Pinned position: saved or card spot, plus drag, clamped.
  readonly property int restX: pinnedX >= 0 ? pinnedX : stageScreenX
  readonly property int restY: pinnedY >= 0 ? pinnedY : stageScreenY
  readonly property int petX: Math.max(0, Math.min(restX + dragDx, pinnedWindow.width - stage.width))
  readonly property int petY: Math.max(0, Math.min(restY + dragDy, pinnedWindow.height - stage.height))

  onOpenedChanged: {
    if (opened) library.rescan()
    else showAll = false
  }
  onPinnedChanged: if (pinned) root.controller.hide()

  function open() {
    if (pinned) saveSetting("pinned", false)
    root.controller.show()
  }

  function toggle() {
    if (pinned || !opened) open()
    else close()
  }

  function dragPet(dx, dy) {
    if (!pinned) return
    dragDx = petX + dx - restX
    dragDy = petY + dy - restY
  }

  function dropPet() {
    if (!pinned) return
    var x = petX
    var y = petY
    dragDx = 0
    dragDy = 0
    saveSetting("pinnedX", x)
    saveSetting("pinnedY", y)
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

  // Reparented between the card and the pinned window.
  Item {
    id: stage
    parent: root.pinned ? pinnedSlot : panelSlot
    x: root.pinned ? root.petX : 0
    y: root.pinned ? root.petY : 0
    width: 192
    height: 208

    PetSprite {
      anchors.fill: parent
      sheetUrl: root.currentPet ? root.currentPet.sheetUrl : ""
      smoothScaling: root.smoothScaling
      running: (root.opened || root.pinned) && root.animate && root.currentPet !== null
      randomBehavior: root.randomBehavior
      onDragged: function(dx, dy) { root.dragPet(dx, dy) }
      onDropped: root.dropPet()
    }

    PanelActionButton {
      visible: !root.pinned
      anchors.top: parent.top
      anchors.right: parent.right
      iconText: "\u{f0403}"
      tooltipText: "Pin to the desktop"
      foreground: root.barForeground
      fontFamily: root.fontFamily
      onClicked: root.saveSetting("pinned", true)
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
      right: true
      bottom: true
    }
    mask: Region {
      x: stage.x
      y: stage.y
      width: stage.width
      height: stage.height
    }

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

        Button {
          visible: root.showAll
          width: parent.width
          leftAlign: true
          iconText: "\uf053"
          text: "Back"
          foreground: root.barForeground
          fontFamily: root.fontFamily
          onClicked: root.showAll = false
        }

        ListView {
          visible: library.pets.length > 0
          width: parent.width
          height: Math.min(contentHeight, Style.space(320))
          spacing: Style.space(4)
          clip: true
          boundsBehavior: Flickable.StopAtBounds
          interactive: contentHeight > height
          model: root.showAll ? library.pets : library.pets.slice(0, root.previewCount)

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

        Button {
          visible: !root.showAll && library.pets.length > root.previewCount
          width: parent.width
          leftAlign: true
          iconText: "\uf054"
          text: "View all " + library.pets.length + " pets"
          foreground: root.barForeground
          fontFamily: root.fontFamily
          onClicked: root.showAll = true
        }

        Toggle {
          width: parent.width
          label: "Smooth scaling"
          description: "Turn off for pixel-art pets"
          checked: root.smoothScaling
          foreground: root.barForeground
          fontFamily: root.fontFamily
          onClicked: root.saveSetting("smooth", !root.smoothScaling)
        }

        Toggle {
          width: parent.width
          label: "Random behaviour"
          description: "A move of its own every 8-20 seconds"
          checked: root.randomBehavior
          foreground: root.barForeground
          fontFamily: root.fontFamily
          onClicked: root.saveSetting("randomBehavior", !root.randomBehavior)
        }

        Toggle {
          width: parent.width
          label: "Animate"
          description: "Off shows one still frame and runs no timer"
          checked: root.animate
          foreground: root.barForeground
          fontFamily: root.fontFamily
          onClicked: root.saveSetting("animate", !root.animate)
        }
      }
    }
  }
}
