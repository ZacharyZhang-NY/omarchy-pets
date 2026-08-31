import QtQuick
import qs.Commons
import qs.Ui

CursorSurface {
  id: row

  property var pet: null
  property string fontFamily: Style.font.family
  property bool smoothScaling: true

  signal clicked()

  hasCursor: mouse.containsMouse
  implicitHeight: content.implicitHeight + Style.spacing.md * 2

  Row {
    id: content
    anchors.verticalCenter: parent.verticalCenter
    anchors.left: parent.left
    anchors.leftMargin: Style.spacing.rowPaddingX
    spacing: Style.spacing.rowGap

    Image {
      anchors.verticalCenter: parent.verticalCenter
      height: Style.space(36)
      width: height * 192 / 208
      source: row.pet ? row.pet.sheetUrl : ""
      sourceClipRect: Qt.rect(0, 0, 192, 208)
      fillMode: Image.PreserveAspectFit
      smooth: row.smoothScaling
      asynchronous: true
    }

    Column {
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.spacing.labelGap

      Text {
        text: row.pet ? row.pet.displayName : ""
        color: row.foreground
        font.family: row.fontFamily
        font.pixelSize: Style.font.body
      }

      Text {
        visible: text !== ""
        text: row.pet ? row.pet.kind : ""
        color: Qt.darker(row.foreground, 1.5)
        font.family: row.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }

  MouseArea {
    id: mouse
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onClicked: row.clicked()
  }
}
