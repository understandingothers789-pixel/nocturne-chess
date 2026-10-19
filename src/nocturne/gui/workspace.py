"""An optional native docking workspace, separate from the classic splitters."""

import base64

from PySide6.QtCore import QByteArray, QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)


class PanelDock(QDockWidget):
    closed = Signal(str)

    def __init__(self, name, title, widget, parent):
        super().__init__(title, parent)
        self.name = name
        self.setObjectName("workspace_" + name)
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setWidget(widget)
        widget.show()
        self.setToolTip("Drag this header to move the panel. Double-click to detach or dock it.")

    def closeEvent(self, event):
        if self.name not in ("database", "graph"):
            event.ignore()
            return
        super().closeEvent(event)
        if event.isAccepted():
            self.closed.emit(self.name)


class DockWorkspace(QWidget):
    finished = Signal()
    reset_requested = Signal()
    panel_closed = Signal(str)

    def __init__(self, panels, parent=None, *, analysis_left=False):
        super().__init__(parent)
        self.setObjectName("dockWorkspace")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.toolbar = QWidget()
        tools = QHBoxLayout(self.toolbar)
        tools.setContentsMargins(6, 0, 6, 0)
        hint = QLabel("Drag panel headers to move or detach. Drag dividers or window edges to resize.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        tools.addWidget(hint, 1)
        for title, signal in (("Reset layout", self.reset_requested), ("Done", self.finished)):
            button = QPushButton(title)
            button.setObjectName("quiet")
            button.setStyleSheet("padding: 5px 10px;")
            button.clicked.connect(lambda checked=False, target=signal: target.emit())
            tools.addWidget(button)
        layout.addWidget(self.toolbar)
        self.surface = QMainWindow()
        self.surface.setObjectName("dockSurface")
        self.surface.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.surface.setDockOptions(QMainWindow.DockOption.AnimatedDocks
                                    | QMainWindow.DockOption.AllowNestedDocks
                                    | QMainWindow.DockOption.AllowTabbedDocks)
        self.surface.setTabPosition(Qt.DockWidgetArea.AllDockWidgetAreas, QTabWidget.TabPosition.North)
        self.surface.setDocumentMode(True)
        layout.addWidget(self.surface, 1)
        self.docks = {}
        for name, (title, widget) in panels.items():
            dock = PanelDock(name, title, widget, self.surface)
            dock.closed.connect(self.panel_closed)
            self.docks[name] = dock
        left, right, bottom = (Qt.DockWidgetArea.LeftDockWidgetArea,
                               Qt.DockWidgetArea.RightDockWidgetArea, Qt.DockWidgetArea.BottomDockWidgetArea)
        board, engine = self.docks["board"], self.docks["analysis"]
        self.surface.addDockWidget(right if analysis_left else left, board)
        self.surface.addDockWidget(left if analysis_left else right, engine)
        self.surface.splitDockWidget(engine, self.docks["database"], Qt.Orientation.Vertical)
        self.surface.splitDockWidget(self.docks["database"], self.docks["graph"], Qt.Orientation.Vertical)
        self.surface.setCorner(Qt.Corner.BottomLeftCorner, bottom)
        self.surface.setCorner(Qt.Corner.BottomRightCorner, bottom)
        self.surface.addDockWidget(bottom, self.docks["moves"])
        self.surface.resizeDocks([board, engine], [650, 800], Qt.Orientation.Horizontal)
        self.surface.resizeDocks([engine, self.docks["database"], self.docks["graph"]],
                                 [550, 180, 85], Qt.Orientation.Vertical)
        self.surface.resizeDocks([self.docks["moves"]], [100], Qt.Orientation.Vertical)
        self.set_editable(True)

    def set_editable(self, editable):
        self.toolbar.setVisible(editable)
        for name, dock in self.docks.items():
            features = QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
            if editable:
                features |= (QDockWidget.DockWidgetFeature.DockWidgetMovable
                             | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
            if name in ("database", "graph"):
                features |= QDockWidget.DockWidgetFeature.DockWidgetClosable
            dock.setFeatures(features)
            dock.setToolTip("Drag this header to move the panel. Double-click to detach or dock it."
                            if editable else "Display → Arrange panels to move this panel.")

    def set_panel_visible(self, name, visible):
        dock = self.docks[name]
        # Do not raise an inactive tab or a floating window on every engine update.
        if dock.isHidden() == visible:
            dock.setVisible(visible)

    def state(self):
        return {"version": 1, "docks": bytes(self.surface.saveState(1).toBase64()).decode("ascii")}

    def restore(self, state):
        if not isinstance(state, dict) or state.get("version") != 1:
            return False
        data = state.get("docks")
        if not isinstance(data, str) or len(data) > 65536:
            return False
        try:
            restored = self.surface.restoreState(QByteArray(base64.b64decode(data, validate=True)), 1)
        except (ValueError, UnicodeError):
            return False
        if restored:
            self.keep_floating_panels_on_screen()
        return restored

    def keep_floating_panels_on_screen(self):
        screens = QApplication.screens()
        if not screens:
            return
        for dock in self.docks.values():
            if not dock.isFloating():
                continue
            rect = dock.frameGeometry()
            if any(screen.availableGeometry().contains(rect.topLeft() + QPoint(40, 12)) for screen in screens):
                continue
            available = screens[0].availableGeometry()
            dock.resize(min(dock.width(), available.width()), min(dock.height(), available.height()))
            dock.move(available.topLeft() + QPoint(12, 12))

    def release(self, parent):
        """Return the original widgets intact, including any detached panels."""
        for dock in self.docks.values():
            dock.hide()
            dock.setFloating(False)
            dock.widget().setParent(parent)
        self.hide()

    def hide_floating_panels(self):
        for dock in self.docks.values():
            if dock.isFloating():
                dock.hide()
