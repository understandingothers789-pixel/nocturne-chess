"""Lichess-style mainline pairs and collapsible inline branches from Game.nodes."""

from html import escape

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QTextBrowser

from ..core.rules import Board
from ..engine.uci_types import plot_score_label, score_label
from .theme import palette
from .wheel import WheelSteps


class MoveTree(QTextBrowser):
    move_clicked = Signal(int)
    move_hovered = Signal(int)
    preview_ended = Signal()
    wheel_navigated = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName("Game move tree and variations")
        self.setToolTip("Click a move to navigate. Wheel steps through the game; Shift+wheel scrolls the notation.")
        self.setMouseTracking(True)
        self.document().setDocumentMargin(3)
        self.collapsed = set()
        self.game = None
        self.light = False
        self.wheel_navigation = True
        self._wheel = WheelSteps()
        self._selected = None
        self._signature = None
        self._pending = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(180)
        self.timer.timeout.connect(self._flush)
        self.anchorClicked.connect(self._click)
        self.highlighted.connect(self._hover)

    def queue_game(self, game, light=False):
        self._pending = (game, light)
        if not self.timer.isActive():
            self.timer.start()

    def _flush(self):
        if self._pending:
            game, light = self._pending
            self._pending = None
            self.set_game(game, light)

    def set_game(self, game, light=False):
        self.timer.stop()
        self._pending = None
        if not self.game or game.id != self.game.id:
            self.collapsed.clear()
            self._selected = None
        self.game, self.light = game, light
        if self._selected != game.current_node:
            self.collapsed.difference_update(game.node_path(game.current_node))
        signature = (game.id, game.current_node, light, frozenset(self.collapsed),
                     tuple((n.san, tuple(n.children), n.evaluation, n.analysis.get("bound"), n.comment, tuple(n.nags))
                           for n in game.nodes))
        if signature == self._signature:
            return
        self._signature = signature
        scroll = self.verticalScrollBar().value()
        selected_changed = self._selected != game.current_node
        self._selected = game.current_node
        colors = palette(light)
        initial = Board(game.initial_fen)

        def number(node):
            offset = node.depth - 1 + (initial.turn < 0)
            return initial.fullmove + offset // 2, offset % 2

        def move(index, with_number=False):
            node = game.nodes[index]
            fullmove, black = number(node)
            prefix = f"{fullmove}{'...' if black else '.'} " if with_number else ""
            style = (f"color:{colors['selected_text']};background-color:{colors['selection']};"
                     if index == game.current_node else f"color:{colors['history']};")
            score = ""
            if node.evaluation is not None:
                turn = initial.turn * (-1 if node.depth % 2 else 1)
                value = (score_label(node.analysis, turn) if node.analysis.get("score_type") in ("cp", "mate")
                         and "score_value" in node.analysis else plot_score_label(node.evaluation))
                score = f' <span style="font-size:11px;color:{colors["metadata"]};">{escape(value)}</span>'
            title = escape(node.comment or node.san, quote=True)
            annotation = "".join({1: "!", 2: "?", 3: "!!", 4: "??", 5: "!?", 6: "?!"}.get(n, "") for n in node.nags)
            return (f'<a name="node-{index}"></a><a href="move:{index}" title="{title}" '
                    f'style="text-decoration:none;{style}">{escape(prefix + node.san + annotation)}</a>{score}')

        output = [f'<div style="font-family:Segoe UI;font-size:14px;color:{colors["history"]};">']
        tasks = [("line", game.nodes[0].children[0], 0)] if game.nodes[0].children else []
        # Root alternatives follow the first mainline row, like other branches.
        while tasks:
            kind, start, level = tasks.pop()
            if kind == "html":
                output.append(start)
                continue
            if kind == "branch":
                collapsed = start in self.collapsed
                marker = "▸" if collapsed else "▾"
                indent = min(level, 8) * 12
                output.append(f'<div style="margin:3px 0 3px {indent}px;color:{colors["metadata"]};">'
                              f'<a href="branch:{start}" style="color:{colors["metadata"]};text-decoration:none;">{marker}</a> ')
                if collapsed:
                    output.append(move(start, True) + " …</div>")
                else:
                    tasks.append(("html", "</div>", 0))
                    tasks.append(("line", start, level))
                continue
            node = start
            events = []
            if level:
                # Alternative continuations stay inline, with nested branches
                # broken out underneath the move that introduces them.
                first = True
                while node is not None:
                    events.append(("html", move(node, first or number(game.nodes[node])[1] == 0) + "  ", 0))
                    if not first:
                        siblings = game.nodes[game.nodes[node].parent].children
                        for child in siblings[1:]:
                            events.append(("branch", child, level + 1))
                    first = False
                    children = game.nodes[node].children
                    node = children[0] if children else None
            else:
                while node is not None:
                    left = node
                    white = number(game.nodes[left])[1] == 0
                    children = game.nodes[left].children
                    right = children[0] if white and children else None
                    number_text = str(number(game.nodes[left])[0])
                    white_text = move(left) if white else "…"
                    black_text = move(right) if right is not None else move(left) if not white else ""
                    events.append(("html", f'<table width="100%" cellspacing="0" cellpadding="4"><tr>'
                                   f'<td width="12%" style="color:{colors["metadata"]};">{number_text}</td>'
                                   f'<td width="44%">{white_text}</td><td width="44%">{black_text}</td>'
                                   '</tr></table>', 0))
                    # Siblings belong to the same move number; never use a
                    # separate game or remembered navigation branch.
                    for index in (left, right):
                        if index is None:
                            continue
                        siblings = game.nodes[game.nodes[index].parent].children
                        for child in siblings[1:]:
                            events.append(("branch", child, 1))
                    end = right if right is not None else left
                    children = game.nodes[end].children
                    node = children[0] if children else None
            tasks.extend(reversed(events))
        if not game.nodes[0].children:
            output.append('<p>Play a move or open a PGN to begin.</p>')
        output.append('</div>')
        self.setHtml("".join(output))
        if selected_changed:
            if game.current_node:
                self.scrollToAnchor(f"node-{game.current_node}")
            else:
                self.verticalScrollBar().setValue(0)
        else:
            self.verticalScrollBar().setValue(scroll)

    def _click(self, url):
        kind, _, value = url.toString().partition(":")
        if not value.isdigit() or not self.game:
            return
        index = int(value)
        if not 0 <= index < len(self.game.nodes):
            return
        if kind == "move":
            self.move_clicked.emit(index)
        elif kind == "branch":
            self.collapsed.symmetric_difference_update({index})
            self.set_game(self.game, self.light)

    def _hover(self, url):
        text = url.toString()
        if text.startswith("move:") and text[5:].isdigit():
            self.move_hovered.emit(int(text[5:]))
        else:
            self.preview_ended.emit()

    def leaveEvent(self, event):
        self.preview_ended.emit()
        self._wheel.reset()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        steps = self._wheel.consume(event) if self.wheel_navigation else None
        if steps is None:
            return super().wheelEvent(event)
        event.accept()
        self.wheel_navigated.emit(steps)
