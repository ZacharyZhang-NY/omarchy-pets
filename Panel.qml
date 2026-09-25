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
  readonly property string petsDir: home + "/.omarchy-pets/pets"
  readonly property var settingKeys: ["petId", "smooth", "pinned", "pinnedX", "pinnedY", "randomBehavior", "animate"]
  readonly property string petId: String(root.setting("petId", ""))
  readonly property bool smoothScaling: root.setting("smooth", true) === true
  readonly property bool animate: root.setting("animate", true) === true
  readonly property bool randomBehavior: root.setting("randomBehavior", true) === true
  readonly property bool pinned: root.setting("pinned", true) === true
  // The pet lives on the desktop while the panel is closed; an open panel shows it inside.
  readonly property bool onDesktop: pinned && !opened
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
  function open() {
    root.controller.show()
  }

  function toggle() {
    if (!opened) open()
    else close()
  }

  function dragPet(dx, dy) {
    if (!onDesktop) return
    dragDx = petX + dx - restX
    dragDy = petY + dy - restY
  }

  function dropPet() {
    if (!onDesktop) return
    var x = petX
    var y = petY
    dragDx = 0
    dragDy = 0
    saveSettings({ pinnedX: x, pinnedY: y })
  }

  // The shell replaces the whole entry, not one key.
  function saveSettings(values) {
    var entry = { id: moduleName }
    for (var i = 0; i < settingKeys.length; i++) if (settingKeys[i] in settings) entry[settingKeys[i]] = settings[settingKeys[i]]
    var changed = false
    for (var name in values) {
      if (entry[name] === values[name]) continue
      entry[name] = values[name]
      changed = true
    }
    if (!changed) return
    var shell = bar ? bar.shell : null
    if (!shell || typeof shell.updateEntryInline !== "function") {
      console.warn("omarchy-pets: cannot save " + JSON.stringify(values) + ": bar.shell.updateEntryInline unavailable")
      return
    }
    if (shell.updateEntryInline(moduleName, entry)) console.log("omarchy-pets: saved " + JSON.stringify(values))
    else console.warn("omarchy-pets: shell refused " + JSON.stringify(values))
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
    parent: root.onDesktop ? pinnedSlot : panelSlot
    x: root.onDesktop ? root.petX : 0
    y: root.onDesktop ? root.petY : 0
    width: 192
    height: 208

    PetSprite {
      id: sprite
      anchors.fill: parent
      sheetUrl: root.currentPet ? root.currentPet.sheetUrl : ""
      sheetLabel: root.currentPet ? root.currentPet.name : ""
      smoothScaling: root.smoothScaling
      running: (root.opened || root.onDesktop) && root.animate && root.currentPet !== null
      randomBehavior: root.randomBehavior
      onDragged: function(dx, dy) { root.dragPet(dx, dy) }
      onDropped: root.dropPet()
    }
  }

  PanelWindow {
    id: pinnedWindow
    visible: root.onDesktop && root.currentPet !== null
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
    // Whole window while engaged, so a fast drag cannot escape.
    mask: Region {
      x: sprite.engaged ? 0 : stage.x
      y: sprite.engaged ? 0 : stage.y
      width: sprite.engaged ? pinnedWindow.width : stage.width
      height: sprite.engaged ? pinnedWindow.height : stage.height
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

      // The card is capped at the screen; what does not fit scrolls, as the clock panel does.
      Flickable {
        id: cardScroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height

      Column {
        id: content
        width: cardScroll.width
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
          textFormat: Text.PlainText
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
          textFormat: Text.PlainText
          text: "No pets in " + root.petsDir + "\nGet omarchy-pets from omarchy-pets.com/cli, then run omarchy-pets install <id>"
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
            onClicked: root.saveSettings({ petId: modelData.name })
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

        Button {
          width: parent.width
          leftAlign: true
          iconText: "\uf08e"
          text: "Open omarchy-pets.com"
          foreground: root.barForeground
          fontFamily: root.fontFamily
          onClicked: Quickshell.execDetached(["omarchy", "launch", "browser", "https://omarchy-pets.com"])
        }

        Toggle {
          width: parent.width
          label: "Show on desktop"
          description: "Stays on the desktop when the panel closes; drag it anywhere"
          checked: root.pinned
          foreground: root.barForeground
          fontFamily: root.fontFamily
          onClicked: root.saveSettings({ pinned: !root.pinned })
        }

        Toggle {
          width: parent.width
          label: "Smooth scaling"
          description: "Turn off for pixel-art pets"
          checked: root.smoothScaling
          foreground: root.barForeground
          fontFamily: root.fontFamily
          onClicked: root.saveSettings({ smooth: !root.smoothScaling })
        }

        Toggle {
          width: parent.width
          label: "Random behaviour"
          description: "A move of its own every 8-20 seconds"
          checked: root.randomBehavior
          foreground: root.barForeground
          fontFamily: root.fontFamily
          onClicked: root.saveSettings({ randomBehavior: !root.randomBehavior })
        }

        Toggle {
          width: parent.width
          label: "Animate"
          description: "Off shows one still frame and runs no timer"
          checked: root.animate
          foreground: root.barForeground
          fontFamily: root.fontFamily
          onClicked: root.saveSettings({ animate: !root.animate })
        }
      }
      }
    }
  }
}
