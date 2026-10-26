"""Clickable move list for browsing a saved game's position preview."""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QTextBrowser

from ..core.variation import mainline
from .notation import html as notation_html
from .theme import palette
from .wheel import WheelSteps


class SavedGameMoves(QTextBrowser):
    """Select a mainline ply by clicking or scrolling; blank clicks return to the end."""

    position_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._wheel_steps = WheelSteps()
        self._game = None
        self._line = []
        self._selected_ply = 0
        self._light = False
        self.anchorClicked.connect(self._activate_move)
        self.setAccessibleName("Saved game moves; click a move or use the mouse wheel to preview positions")

    @property
    def selected_ply(self):
        return self._selected_ply

    def set_game(self, game, light=False):
        self._game = game
        self._line = mainline(game.nodes)
        self._light = light
        self.select_ply(len(self._line) - 1, emit=False)

    def select_ply(self, ply, *, emit=True):
        if not self._line:
            self._selected_ply = 0
            self.clear()
            return
        self._selected_ply = max(0, min(len(self._line) - 1, ply))
        self._render()
        if emit:
            self.position_selected.emit(self._selected_ply)

    def _activate_move(self, url):
        text = url.toString()
        if text.startswith("ply:") and text[4:].isdigit():
            self.select_ply(int(text[4:]))

    def _render(self):
        if self._game is None:
            return
        scroll = self.verticalScrollBar().value()
        colors = palette(self._light)
        position = self._game.position_at_node(0)
        tokens = []
        for ply, node_id in enumerate(self._line[1:], 1):
            node = self._game.nodes[node_id]
            move_number = position.fullmove
            prefix = f"{move_number}. " if position.turn > 0 else f"{move_number}... "
            if ply == self._selected_ply:
                style = (f"color:{colors['selected_text']}; background-color:{colors['selection']};"
                         "text-decoration:none; border-radius:2px;")
            else:
                style = f"color:{colors['history']}; text-decoration:none;"
            tokens.append(f'<a href="ply:{ply}" style="{style}">{prefix}{notation_html(node.san, size=15)}</a>')
            position.push(node.move)
        body = " ".join(tokens) if tokens else '<span style="color:%s;">No moves in this game.</span>' % colors["muted"]
        self.setHtml(f'<div style="font-family:Consolas,monospace; font-size:14px; line-height:150%; '
                     f'white-space:pre-wrap;">{body}</div>')
        self.verticalScrollBar().setValue(scroll)

    def wheelEvent(self, event):
        if self._step_wheel(event):
            return
        super().wheelEvent(event)

    def _step_wheel(self, event):
        steps = self._wheel_steps.consume(event)
        if steps is None:
            return False
        event.accept()
        if steps and self._line:
            self.select_ply(self._selected_ply + steps)
        return True

    def eventFilter(self, watched, event):
        if watched is self.viewport() and event.type() == QEvent.Type.Wheel:
            if self._step_wheel(event):
                return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        is_blank = (event.button() == Qt.MouseButton.LeftButton
                    and not self.anchorAt(event.position().toPoint()))
        super().mousePressEvent(event)
        if is_blank:
            self.select_ply(len(self._line) - 1)
