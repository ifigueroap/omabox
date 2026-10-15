import QtQuick
import qs.Commons
import qs.Commons as Commons

// Bar slot for a third-party plugin. qs.Ui.BarWidget and qs.Ui.WidgetButton
// are component types, and those are not visible to a file under
// ~/.config/omarchy/plugins/ (the same limit as ShellIpc). The bar host
// injects `bar` (PluginBarApi for third-party widgets) and calls
// triggerPress on the widget item itself.
Item {
  id: root

  property var bar: null
  property string moduleName: "omabox"
  property var settings: ({})
  property bool interactive: true
  property bool pressable: true

  implicitWidth: Style.space(32)
  implicitHeight: Style.space(32)

  function triggerPress(button) {
    if (button !== Qt.LeftButton) return
    if (root.bar && root.bar.hideTooltip) root.bar.hideTooltip(root)
    if (root.bar && root.bar.run) root.bar.run("omabox toggle")
  }

  HoverHandler {
    onHoveredChanged: {
      if (!root.bar) return
      if (hovered && root.bar.showTooltip) root.bar.showTooltip(root, "Omabox")
      else if (root.bar.hideTooltip) root.bar.hideTooltip(root)
    }
  }

  Item {
    anchors.centerIn: parent
    width: Style.space(14)
    height: Style.space(14)

    Rectangle {
      anchors.fill: parent
      radius: Style.space(3)
      color: "transparent"
      border.color: root.bar ? root.bar.foreground : Commons.Color.foreground
      border.width: Math.max(1, Style.normalBorderWidth)
    }

    Rectangle {
      anchors.centerIn: parent
      width: Style.space(4)
      height: Style.space(4)
      radius: width / 2
      color: root.bar ? root.bar.foreground : Commons.Color.foreground
    }
  }
}
