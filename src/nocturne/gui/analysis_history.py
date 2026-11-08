"""Optional interactive node checkpoints and bounded, cancellable tactic scans."""
from copy import deepcopy
from collections import OrderedDict

import chess
from PySide6.QtCore import QTimer, Signal, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
                              QPushButton, QComboBox, QLabel, QSizePolicy)
from .candidates import CandidatePanel
from .moves import MoveText
from ..snapshots import node_label


def tactic_patterns(fen, pv, plies=12, min_ply=4):
    """Conservative pattern hints, not engine proof of a sound combination."""
    board = chess.Board(fen)
    values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
              chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
    found = []
    for ply, uci in enumerate(pv[:plies], 1):
        move = board.parse_uci(uci)
        color = board.turn
        piece = board.piece_at(move.from_square)
        san = board.san(move)
        captured = board.piece_at(move.to_square)
        old_pins = {s for s in chess.SQUARES if board.color_at(s) == (not color)
                    and board.is_pinned(not color, s)}
        old_attacks = {(s, t) for s in chess.SQUARES if board.color_at(s) == color
                       and s != move.from_square for t in board.attacks(s)
                       if board.color_at(t) == (not color)}
        board.push(move)
        prefix = f'{san} · ply {ply}'
        if board.is_checkmate():
            found.append((ply, f'Mate on this line · {prefix}'))
        targets = [s for s in board.attacks(move.to_square)
                   if board.piece_at(s) and board.color_at(s) != color
                   and values[board.piece_type_at(s)] > values[piece.piece_type]]
        if len(targets) >= 2:
            found.append((ply, f'Fork pattern · {prefix}'))
        for square in chess.SQUARES:
            if (board.color_at(square) == (not color) and square not in old_pins
                    and board.is_pinned(not color, square)):
                found.append((ply, f'Absolute pin pattern · {prefix}'))
                break
        revealed = [(s, t) for s in chess.SQUARES if board.color_at(s) == color
                    and s != move.to_square for t in board.attacks(s)
                    if board.color_at(t) == (not color) and (s, t) not in old_attacks
                    and board.piece_type_at(s) in (chess.BISHOP, chess.ROOK, chess.QUEEN)
                    and values[board.piece_type_at(t)] >= 3]
        if revealed and not board.is_check():
            found.append((ply, f'Discovered attack pattern · {prefix}'))
        attackers = board.attackers(color, board.king(not color))
        if board.is_check() and move.to_square not in attackers:
            found.append((ply, f'Discovered check · {prefix}'))
        # Only flag an actual capture of the offered piece on the next ply;
        # exclude equal exchanges and immediate material recovery.
        if ply < len(pv) and not captured:
            reply = board.parse_uci(pv[ply])
            if reply.to_square == move.to_square and board.is_capture(reply):
                after = board.copy()
                after.push(reply)
                recovery = 0
                if ply + 1 < len(pv):
                    recapture = after.parse_uci(pv[ply + 1])
                    victim = after.piece_at(recapture.to_square)
                    recovery = values.get(victim.piece_type, 0) if victim else 0
                if recovery < values[piece.piece_type]:
                    found.append((ply, f'Possible {chess.piece_name(piece.piece_type)} sacrifice · {prefix}'))
    return [(ply, text) for ply, text in found if ply >= min_ply]


class AnalysisHistory(QWidget):
    viewing = Signal(bool)
    preview = Signal(list, int, str)
    preview_end = Signal()
    insert = Signal(list)

    def __init__(self, busy, parent=None):
        super().__init__(parent)
        self.busy = busy
        self.records = OrderedDict()
        self.key = None
        self.session = None
        self.selected = None
        self.anchor = []
        self.root = None
        self.live = {}
        self.checkpoints = {}
        self.next_nodes = 1_000_000
        self.scanning = False
        self.min_ply, self.max_ply = 4, 12
        self.scan_token = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(40)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabs = QWidget()
        self.tabs_layout = QHBoxLayout(self.tabs)
        self.tabs_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self.tabs)
        layout.addWidget(scroll)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(['Rank at that time', 'Keep moves in place'])
        self.mode.currentIndexChanged.connect(self._mode_changed)
        row.addWidget(self.mode)
        self.find = QPushButton('Find tactics')
        self.find.setToolTip('Stop analysis first. Check the configured ply range of each displayed line for tactical patterns and possible sacrifices; results are not engine verification.')
        self.find.clicked.connect(self.scan)
        row.addWidget(self.find)
        self.reorder = QPushButton('Update move order')
        self.reorder.clicked.connect(self._mode_changed)
        self.reorder.hide()
        row.addWidget(self.reorder)
        self.caption = QLabel('Viewing: Live')
        row.addWidget(self.caption)
        layout.addLayout(row)
        self.panel = CandidatePanel(MoveText(auto_fit=True))
        self.panel.show_line_depth = True
        self.panel.preview.connect(self._preview)
        self.panel.preview_end.connect(self.preview_end)
        self.panel.navigate.connect(self._insert)
        self.panel.set_maia(enabled=False)
        self.panel.hide()
        layout.addWidget(self.panel)
        self.results = QVBoxLayout()
        layout.addLayout(self.results)
        self.poll = QTimer(self)
        self.poll.setInterval(250)
        self.poll.timeout.connect(self._availability)
        self.poll.start()
        self._buttons()

    def position(self, key, fen, turn):
        if self.key == key:
            return
        self.cancel()
        self.key = key
        self.root, self.turn = fen, turn
        self.session = None
        self.live = {}
        self.checkpoints = self.records.setdefault(key, {})
        self.records.move_to_end(key)
        while len(self.records) > 128:
            self.records.popitem(last=False)
        self.next_nodes = max(self.checkpoints, default=500_000) * 2
        self.anchor = []
        self.select(None)

    def observe(self, session, lines, nodes):
        if self.session != session:
            self.session = session
            self.checkpoints.clear()
            self.next_nodes = 1_000_000
            self.select(None)
        self.live = deepcopy(lines)
        if self.mode.currentIndex() and not self.anchor:
            self.anchor = [x['pv'][0] for _, x in sorted(lines.items()) if x.get('pv')]
        crossed = None
        while nodes >= self.next_nodes:
            crossed = self.next_nodes
            self.next_nodes *= 2
        if crossed is not None:
            # A single output must never masquerade as multiple checkpoints.
            self.checkpoints[crossed] = (nodes, deepcopy(lines))
            self._buttons()
        if self.selected is None and self.mode.currentIndex():
            self._render()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _buttons(self):
        self._clear_layout(self.tabs_layout)
        for value in [None] + list(self.checkpoints):
            button = QPushButton('Live' if value is None else node_label(value))
            button.setCheckable(True)
            button.setChecked(self.selected == value)
            if value is not None:
                actual, lines = self.checkpoints[value]
                button.setToolTip(f'First captured output at {actual:,} nodes. {len(lines)} MultiPV lines; individual lines may have different depths.')
            button.clicked.connect(lambda checked=False, v=value: self.select(v))
            self.tabs_layout.addWidget(button)
        self.tabs_layout.addStretch()

    def select(self, value):
        self.cancel()
        self.selected = value
        self.preview_end.emit()
        self._buttons()
        self._render()

    def _mode_changed(self):
        self.anchor = [x['pv'][0] for _, x in sorted(self.live.items()) if x.get('pv')]
        self.reorder.setVisible(bool(self.mode.currentIndex()))
        self.select(self.selected)

    def shown(self):
        return self.live if self.selected is None else self.checkpoints[self.selected][1]

    def _render(self):
        historical = self.selected is not None or bool(self.mode.currentIndex())
        self.viewing.emit(historical)
        self.panel.setVisible(historical)
        self.caption.setText('Viewing: ' + ('Live' if self.selected is None else node_label(self.selected)))
        if not historical:
            return
        self.panel.clear()
        lines = self.shown()
        self.panel.set_multipv(max(1, len(lines), len(self.anchor)))
        self.panel.reserve_slots(max(1, len(lines), len(self.anchor)))
        self.panel.pinned.clear()
        if self.mode.currentIndex():
            by_move = {x['pv'][0]: x for x in lines.values() if x.get('pv')}
            for rank, move in enumerate(self.anchor, 1):
                info = by_move.get(move)
                if info:
                    self.panel.update_line(dict(info, multipv=rank), self.turn)
                    header = self.panel.rows[rank][1]
                    header.setText(f'Rank at checkpoint: #{info["multipv"]}')
                    header.show()
                else:
                    name = chess.Board(self.root).san(chess.Move.from_uci(move))
                    self.panel.rows[rank][2].setText(f'{name} — Not in captured MultiPV')
        else:
            for info in lines.values():
                self.panel.update_line(info, self.turn)
        self.panel.pinned.update(self.panel.lines)

    def _preview(self, rank, ply):
        info = self.panel.lines.get(rank)
        if info:
            self.preview.emit(info['pv'], ply, 'Analysis checkpoint')

    def _insert(self, rank, ply):
        info = self.panel.lines.get(rank)
        if info:
            self.insert.emit(info['pv'][:ply])

    def _availability(self):
        if self.busy() and self.scanning:
            self.cancel()
        self.find.setEnabled(self.scanning or (not self.busy() and bool(self.live or self.checkpoints)))

    def cancel(self):
        self.scan_token += 1
        self.scanning = False
        self.find.setText('Find tactics')
        self._clear_layout(self.results)

    def scan(self):
        if self.scanning:
            self.cancel()
            return
        if self.busy() or not self.root:
            return
        self.cancel()
        self.scanning = True
        self.find.setText('Cancel')
        token = self.scan_token
        tasks = iter(sorted(deepcopy(self.shown()).items()))
        note = QLabel(f'Checking plies {self.min_ply}–{self.max_ply} per line. Pattern hints, not verified combinations.')
        note.setWordWrap(True)
        self.results.addWidget(note)

        def step():
            if token != self.scan_token or self.busy():
                if token == self.scan_token:
                    self.cancel()
                return
            task = next(tasks, None)
            if task is None:
                self.scanning = False
                self.find.setText('Find tactics')
                return
            rank, info = task
            try:
                hints = tactic_patterns(self.root, info['pv'], self.max_ply, self.min_ply)
            except ValueError:
                hints = []
            if not hints:
                self.results.addWidget(QLabel(f'Line {rank}: no clear pattern found within checked moves.'))
            for ply, text in hints:
                button = QPushButton(f'Line {rank}: {text}')
                button.setToolTip(text)
                button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                button.clicked.connect(lambda checked=False, p=info['pv'], n=ply: self.preview.emit(p, n, 'Tactic pattern'))
                self.results.addWidget(button)
            QTimer.singleShot(0, self, step)
        QTimer.singleShot(0, self, step)
