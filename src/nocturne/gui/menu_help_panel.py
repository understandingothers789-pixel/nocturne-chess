"""Noninteractive menu explanations positioned outside the menu cascade."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from .theme import palette


class MenuHelpPanel(QFrame):
    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName('menuExplanation')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        self.title.setStyleSheet('font-weight: 600;')
        self.description = QLabel()
        self.description.setTextFormat(Qt.TextFormat.PlainText)
        self.description.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.description)
        self.setFixedWidth(270)

    def show_help(self, title, description, menu, root, action):
        light = self.parentWidget().config.get("light", False)
        if light != getattr(self, "_last_light", None):
            self._last_light = light
            colors = palette(light)
            self.setStyleSheet("QFrame#menuExplanation { background: %s; border: 1px solid %s; border-radius: 6px; } QLabel { color: %s; background: transparent; border: none; }" % (colors["raised"], colors["border"], colors["text"]))
        self.title.setText(title)
        self.description.setText(description)
        self.adjustSize()
        screen = menu.screen().availableGeometry()
        # Anchor to the outside of the entire cascade so parent menus stay usable.
        x = root.geometry().left() - self.width() - 10
        y = menu.geometry().top() + menu.actionGeometry(action).top()
        if x < screen.left():
            # File/Tree at the screen edge have no left-hand room: use space below.
            x = root.geometry().left()
            y = root.geometry().bottom() + 10
            if y + self.height() > screen.bottom():
                x = menu.geometry().right() + 10
                y = menu.geometry().top()
        x = max(screen.left(), min(x, screen.right() - self.width() + 1))
        y = max(screen.top(), min(y, screen.bottom() - self.height() + 1))
        self.move(x, y)
        self.show()
