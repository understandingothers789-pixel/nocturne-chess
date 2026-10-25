"""Scrollable move pairs with branch rows and saved, White-perspective scores."""
from html import escape

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QTextBrowser

from .moves import MoveText
from .theme import palette
from ..core.rules import Board
from ..engine.uci_types import plot_score_label


class GameLine(MoveText):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Game line: move pairs, variations and evaluations")
        self._game_signature = None
        self._pending_game = None
        self._eval_refresh = QTimer(self)
        self._eval_refresh.setSingleShot(True)
        self._eval_refresh.setInterval(500)
        self._eval_refresh.timeout.connect(self._refresh_saved_values)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def refresh_evaluation(self, game):
        self._pending_game = game
        if not self._eval_refresh.isActive():
            self._eval_refresh.start()

    def _refresh_saved_values(self):
        game = self._pending_game
        self._pending_game = None
        if self.isVisible() and game is not None and self._game_signature and game.id == self._game_signature[0]:
            self.set_game(game, self._light, self._book_departures)

    def wheelEvent(self, event):
        # The board and bottom PGN keep navigation; this panel scrolls its text.
        self.cancel_preview()
        QTextBrowser.wheelEvent(self, event)
        event.accept()

    def set_game(self, game, light=False, book_departures=None):
        departures = dict(book_departures or {})
        self._book_departures = departures
        nodes = game.nodes
        current = game.current_node
        signature = (game.id, current, light, tuple(sorted(departures.items())),
                     tuple((node.parent, tuple(node.children), node.san, node.evaluation, tuple(node.nags))
                           for node in nodes))
        if signature == self._game_signature:
            return
        previous_current = self._current
        previous_game = self._game_signature[0] if self._game_signature else None
        scroll = self.verticalScrollBar().value()
        self._game_signature = signature
        self._current = current
        self._light = light
        self._items = [(node.san, i) for i, node in enumerate(nodes) if i]
        self.cancel_preview()
        colors = palette(light)
        root = Board(game.initial_fen)
        offset = int(root.turn < 0)
        rows = []

        def cell(index, indent):
            if index is None:
                return '<td width="44%"></td>'
            node = nodes[index]
            active = index == current
            bg = colors['selection'] if active else colors['soft'] if indent else colors['panel']
            fg = colors['selected_text'] if active else colors['history']
            if index in departures:
                fg = '#87713f' if light else '#c3b07c'
            value = plot_score_label(node.evaluation) if node.evaluation is not None else ''
            title = departures.get(index, '')
            punctuation = {1: "!", 2: "?", 3: "!!", 4: "??", 5: "!?", 6: "?!"}
            text = ('&nbsp;' * (2 * min(indent, 5))
                    + escape(node.san + "".join(punctuation.get(nag, f" ${nag}") for nag in node.nags)))
            # Use a nested two-cell table to align the evaluation at the right
            # of each move without relying on unsupported CSS floats.
            return (f'<td width="44%" bgcolor="{bg}"><a name="node{index}"></a>'
                    f'<table width="100%" cellspacing="0" cellpadding="4"><tr>'
                    f'<td><a href="move:{index}" title="{escape(title, quote=True)}" '
                    f'style="color:{fg};text-decoration:none;">{text}</a></td>'
                    f'<td align="right"><span style="font-size:11px;color:{colors["muted"]};">'
                    f'{escape(value)}</span></td></tr></table></td>')

        # Iterative traversal keeps nested variations safe even in large PGNs.
        stack = [(nodes[0].children[0], 0)] if nodes[0].children else []
        while stack:
            first, indent = stack.pop()
            node = nodes[first]
            white = (node.depth - 1 + offset) % 2 == 0
            paired = node.children[0] if white and node.children else None
            last = paired if paired is not None else first
            number = root.fullmove + (node.depth - 1 + offset) // 2
            branches = []
            parent = nodes[node.parent]
            if parent.children[0] == first:
                branches.extend(parent.children[1:])
            if paired is not None:
                branches.extend(node.children[1:])
            prefix = ('│&nbsp;' * min(indent, 5)) + ('↳&nbsp;' if indent else '')
            rows.append(f'<tr><td width="12%" valign="middle" style="color:{colors["muted"]};'
                        f'font-size:11px;">{prefix}{number}{"…" if not white else "."}</td>'
                        + cell(first if white else None, indent)
                        + cell(paired if white else first, indent) + '</tr>')
            if nodes[last].children:
                stack.append((nodes[last].children[0], indent))
            stack.extend((child, indent + 1) for child in reversed(branches))
        self.setHtml('<div style="font-family:Segoe UI,sans-serif;font-size:14px;">'
                     '<table width="100%" cellspacing="1" cellpadding="0">'
                     + ''.join(rows) + '</table></div>')
        if (previous_current != current or previous_game != game.id) and current:
            self.scrollToAnchor(f'node{current}')
        else:
            self.verticalScrollBar().setValue(scroll)

    def scrollToAnchor(self, name):
        # QTextBrowser normally aligns an anchor at the top. Centering the
        # selected move leaves useful context on both sides after a click.
        super().scrollToAnchor(name)
        self.verticalScrollBar().setValue(max(0, self.verticalScrollBar().value() - self.viewport().height() // 3))
