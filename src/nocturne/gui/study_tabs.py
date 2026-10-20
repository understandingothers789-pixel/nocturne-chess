"""Native movable tabs with live text rendering instead of Qt's drag bitmap."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionTab, QStylePainter, QTabBar, QWidget

from .theme import palette


class StudyTabBar(QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("studyTabs")
        self._drag_index = -1
        self.tabMoved.connect(self._moved)

    def _moved(self, source, destination):
        if self._drag_index == source:
            self._drag_index = destination
        elif source < self._drag_index <= destination:
            self._drag_index -= 1
        elif destination <= self._drag_index < source:
            self._drag_index += 1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_index = self.tabAt(event.position().toPoint())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._drag_index = -1

    def childEvent(self, event):
        super().childEvent(event)
        # Qt exposes its internal moving-tab overlay as a plain QWidget.
        # The other direct children are buttons and retain their native paint.
        if event.added() and isinstance(event.child(), QWidget):
            event.child().installEventFilter(self)

    def eventFilter(self, watched, event):
        if (event.type() == QEvent.Type.Paint
                and type(watched) is QWidget and watched.parentWidget() is self
                and 0 <= self._drag_index < self.count()):
            option = QStyleOptionTab()
            self.initStyleOption(option, self._drag_index)
            option.position = QStyleOptionTab.TabPosition.Moving
            overlap = self.style().pixelMetric(QStyle.PixelMetric.PM_TabBarTabOverlap, None, self)
            option.rect.moveTopLeft(watched.rect().topLeft())
            option.rect.translate(overlap, 0)
            painter = QStylePainter(watched)
            light = bool(QApplication.instance().property("nocturneLightAppearance"))
            painter.fillRect(watched.rect(), QColor(palette(light)["bg"]))
            # Draw at the widget's actual device pixel ratio and position.
            # Qt's default path composites a cached alpha pixmap instead.
            self.style().drawControl(QStyle.ControlElement.CE_TabBarTab, option, painter, self)
            painter.end()
            return True
        return super().eventFilter(watched, event)
