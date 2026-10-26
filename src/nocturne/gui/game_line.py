"""Scrollable move pairs with branch rows and saved, White-perspective scores."""
from html import escape

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import QTextBrowser

from .moves import MoveText
from .theme import palette
from ..core.rules import Board
from ..engine.uci_types import plot_score_label


class GameLine(MoveText):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Game line: move pairs, variations and evaluations")
        self._branch_guides = []
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
        row_paths = []

        def figurine(san):
            return san.translate(str.maketrans({"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘"}))

        def cell(index, indent):
            if index is None:
                return f'<td width="44%" bgcolor="{colors["soft"] if indent else colors["panel"]}"></td>'
            node = nodes[index]
            active = index == current
            bg = colors['selection'] if active else colors['soft'] if indent else colors['panel']
            fg = colors['selected_text'] if active else ('#cbd9dc' if not light else '#334b50')
            if index in departures:
                fg = '#87713f' if light else '#c3b07c'
            value = plot_score_label(node.evaluation) if node.evaluation is not None else ''
            title = departures.get(index, '')
            punctuation = {1: "!", 2: "?", 3: "!!", 4: "??", 5: "!?", 6: "?!"}
            text = escape(figurine(node.san) + "".join(punctuation.get(nag, f" ${nag}") for nag in node.nags))
            # Use a nested two-cell table to align the evaluation at the right
            # of each move without relying on unsupported CSS floats.
            return (f'<td width="44%" bgcolor="{bg}"><a name="node{index}"></a>'
                    f'<table width="100%" cellspacing="0" cellpadding="5"><tr>'
                    f'<td><a href="move:{index}" title="{escape(title, quote=True)}" '
                    f'style="color:{fg};text-decoration:none;">{text}</a></td>'
                    f'<td align="right"><span style="font-size:11px;color:{colors["muted"]};">'
                    f'{escape(value)}</span></td></tr></table></td>')

        def variation_move(index, first=False):
            node = nodes[index]
            white = (node.depth - 1 + offset) % 2 == 0
            number = root.fullmove + (node.depth - 1 + offset) // 2
            prefix = f"{number}." if white else f"{number}…" if first else ""
            active = index == current
            fg = colors['selected_text'] if active else ('#cbd9dc' if not light else '#334b50')
            bg = f"background-color:{colors['selection']};" if active else ""
            punctuation = {1: "!", 2: "?", 3: "!!", 4: "??", 5: "!?", 6: "?!"}
            san = escape(figurine(node.san) + "".join(punctuation.get(n, f" ${n}") for n in node.nags))
            value = plot_score_label(node.evaluation) if node.evaluation is not None else ''
            title = departures.get(index, '')
            if value:
                title = f"{title} · {value}" if title else value
            return (f'<a name="node{index}"></a><a href="move:{index}" '
                    f'title="{escape(title, quote=True)}" style="color:{fg};{bg}'
                    f'text-decoration:none;">{prefix}{"&nbsp;" if prefix else ""}{san}</a>')

        # Iterative traversal keeps nested variations safe even in large PGNs.
        stack = [(nodes[0].children[0], ())] if nodes[0].children else []
        while stack:
            first, path = stack.pop()
            indent = len(path)
            if indent:
                # A variation reads as a sentence. Only a fork interrupts it;
                # natural wrapping handles the available panel width.
                run = []
                index = first
                while True:
                    run.append(index)
                    if len(nodes[index].children) != 1:
                        break
                    index = nodes[index].children[0]
                gutter = min(3 + 3 * indent, 30)
                size = 14 if indent == 1 else 13
                text = '&nbsp; '.join(variation_move(i, j == 0) for j, i in enumerate(run))
                rows.append(f'<table width="100%" cellspacing="0" cellpadding="0"><tr>'
                            f'<td width="{gutter}%"></td><td width="{100-gutter}%" '
                            f'bgcolor="{('#202d37' if not light else '#eef2ef')}" style="font-size:{size}px;">'
                            f'<p style="margin-top:7px;margin-bottom:7px;">'
                            f'<a name="row{first}"></a>{text}'
                            f'<a name="rowend{first}"></a></p></td></tr></table>')
                row_paths.append((first, path))
                children = nodes[run[-1]].children
                if children:
                    stack.append((children[0], path))
                    stack.extend((child, path + (child,)) for child in reversed(children[1:]))
                continue
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
            # A single gutter belongs to the entire branch, rather than
            # repeating tree glyphs inside each move-number cell.
            gutter = min(3 + 3 * indent, 30)
            row = (f'<table width="100%" cellspacing="0" cellpadding="0"><tr>'
                   f'<td width="{gutter}%"></td><td width="{100-gutter}%">'
                   f'<table width="100%" cellspacing="0" cellpadding="0"><tr>'
                   f'<td width="12%" style="color:{colors["muted"]};'
                   f'font-size:11px;"><a name="row{first}"></a>{number}{"…" if not white else "."}</td>'
                   + cell(first if white else None, indent)
                   + cell(paired if white else first, indent) + '</tr></table></td></tr></table>')
            rows.append(row)
            row_paths.append((first, path))
            if nodes[last].children:
                stack.append((nodes[last].children[0], path))
            stack.extend((child, path + (child,)) for child in reversed(branches))
        self.setHtml(f'<body bgcolor="{colors["panel"]}"><div style="font-family:Segoe UI,sans-serif;font-size:14px;">'
                     + ''.join(rows) + '</div></body>')
        anchors = {}
        ends = {}
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                for name in fragment.charFormat().anchorNames():
                    if name.startswith('row') and not name.startswith('rowend'):
                        cursor = QTextCursor(self.document())
                        cursor.setPosition(fragment.position())
                        anchors[int(name[3:])] = cursor
                for name in fragment.charFormat().anchorNames():
                    if name.startswith("rowend"):
                        cursor = QTextCursor(self.document())
                        cursor.setPosition(fragment.position())
                        ends[int(name[6:])] = cursor
                iterator += 1
            block = block.next()
        groups = {}
        for first, path in row_paths:
            if first in anchors:
                for depth, branch in enumerate(path):
                    groups.setdefault((depth, branch), []).append(anchors[first])
                    if first in ends:
                        groups[(depth, branch)].append(ends[first])
        self._branch_guides = [(depth, cursors)
                               for (depth, _), cursors in groups.items()]
        self.viewport().update()
        if (previous_current != current or previous_game != game.id) and current:
            self.scrollToAnchor(f'node{current}')
        else:
            self.verticalScrollBar().setValue(scroll)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setPen(QPen(QColor('#b4c4c1' if self._light else '#3c5961'), 1))
        for depth, cursors in self._branch_guides:
            first, last = cursors[0], cursors[-1]
            top = self.cursorRect(first).center().y()
            bottom = self.cursorRect(last).center().y()
            x = self.cursorRect(first).left() - 10
            painter.drawLine(x, top - 10, x, bottom)
            for cursor in cursors:
                y = self.cursorRect(cursor).center().y()
                if self.cursorRect(cursor).left() == self.cursorRect(first).left():
                    painter.drawLine(x, y, x + 7, y)
        painter.end()

    def scrollToAnchor(self, name):
        # QTextBrowser normally aligns an anchor at the top. Centering the
        # selected move leaves useful context on both sides after a click.
        super().scrollToAnchor(name)
        self.verticalScrollBar().setValue(max(0, self.verticalScrollBar().value() - self.viewport().height() // 3))
