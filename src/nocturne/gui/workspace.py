"""An optional native docking workspace, separate from the classic splitters."""

import base64

from PySide6.QtCore import QByteArray, QPoint, Qt, QTimer, Signal
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
        # Surplus desktop width belongs beyond the working columns, rather
        # than becoming margins on either side of the square chessboard.
        center = QWidget()
        center.setMaximumSize(0, 0)
        self.surface.setCentralWidget(center)
        layout.addWidget(self.surface, 1)
        self.docks = {}
        for name, (title, widget) in panels.items():
            dock = PanelDock(name, title, widget, self.surface)
            dock.closed.connect(self.panel_closed)
            dock.topLevelChanged.connect(
                lambda floating, panel=dock: panel.setMaximumWidth(16777215) if floating
                else QTimer.singleShot(0, self.fit_columns))
            self.docks[name] = dock
        left, bottom = Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.BottomDockWidgetArea
        board, engine = self.docks["board"], self.docks["analysis"]
        self.surface.addDockWidget(left, engine if analysis_left else board)
        self.surface.splitDockWidget(engine if analysis_left else board,
                                     board if analysis_left else engine, Qt.Orientation.Horizontal)
        if "insights" in self.docks:
            self.surface.splitDockWidget(board if analysis_left else engine, self.docks["insights"], Qt.Orientation.Horizontal)
        self.surface.splitDockWidget(self.docks.get("insights", engine), self.docks["database"], Qt.Orientation.Vertical)
        self.surface.splitDockWidget(engine, self.docks["graph"], Qt.Orientation.Vertical)
        self.surface.setCorner(Qt.Corner.BottomLeftCorner, bottom)
        self.surface.setCorner(Qt.Corner.BottomRightCorner, bottom)
        self.surface.addDockWidget(bottom, self.docks["moves"])
        self.surface.resizeDocks([board, engine], [650, 800], Qt.Orientation.Horizontal)
        self.surface.resizeDocks([engine, self.docks["database"], self.docks["graph"]],
                                 [550, 180, 85], Qt.Orientation.Vertical)
        self.surface.resizeDocks([self.docks["moves"]], [100], Qt.Orientation.Vertical)
        self.set_editable(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.fit_columns)

    def fit_columns(self):
        board = self.docks["board"]
        if not getattr(self.window(), "analysis_mode", False):
            for dock in self.docks.values():
                dock.setMaximumWidth(16777215)
            return
        # Respect detached, tabbed and freely rearranged board panels.
        if board.isFloating() or self.surface.tabifiedDockWidgets(board):
            return
        arena = board.widget()
        view = getattr(self.window(), "board_view", None)
        if view is None or not view.isVisible():
            return
        target = max(350, view.height() + arena.width() - view.width())
        if board.maximumWidth() != target:
            board.setMaximumWidth(target)
        for name in ("analysis", "database", "graph"):
            dock = self.docks[name]
            if not dock.isFloating():
                dock.setMaximumWidth(16777215)
        key = (self.width(), self.height(), target)
        if getattr(self, "_fit_key", None) != key:
            self._fit_key = key
            columns, widths = [board], [target]
            remaining = max(560, self.width() - target - 24)
            has_insights = "insights" in self.docks and not self.docks["insights"].isHidden()
            insights_width = max(280, round(remaining * 0.38)) if has_insights else 0
            for name, width in (("analysis", remaining - insights_width), ("insights", insights_width)):
                dock = self.docks.get(name)
                if dock is not None and not dock.isFloating() and not dock.isHidden():
                    columns.append(dock)
                    widths.append(width)
            self.surface.resizeDocks(columns, widths, Qt.Orientation.Horizontal)

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
        return {"version": 1, "maia_tools": 1, "docks": bytes(self.surface.saveState(1).toBase64()).decode("ascii")}

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
            self._fit_key = None
            # Migrate the old two-sided default dock arrangement. Keep custom
            # floating/tabbed layouts intact, including their saved positions.
            board, engine = self.docks["board"], self.docks["analysis"]
            if (not board.isFloating() and not engine.isFloating()
                    and not self.surface.tabifiedDockWidgets(board)
                    and all(not self.docks[name].isFloating()
                            and not self.surface.tabifiedDockWidgets(self.docks[name])
                            for name in ("analysis", "database", "graph"))
                    and self.surface.dockWidgetArea(board) != self.surface.dockWidgetArea(engine)):
                analysis_left = self.surface.dockWidgetArea(board) == Qt.DockWidgetArea.RightDockWidgetArea
                first, second = (engine, board) if analysis_left else (board, engine)
                self.surface.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, first)
                self.surface.splitDockWidget(first, second, Qt.Orientation.Horizontal)
                self.surface.splitDockWidget(self.docks.get("insights", engine), self.docks["database"], Qt.Orientation.Vertical)
                self.surface.splitDockWidget(engine, self.docks["graph"], Qt.Orientation.Vertical)
            if "insights" in self.docks and not state.get("maia_tools"):
                self.surface.splitDockWidget(self.docks["analysis"], self.docks["insights"], Qt.Orientation.Horizontal)
            self.keep_floating_panels_on_screen()
            QTimer.singleShot(0, self.fit_columns)
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
