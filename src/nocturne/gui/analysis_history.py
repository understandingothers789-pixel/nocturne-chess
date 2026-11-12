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


def exchange_description(white_lost, black_lost):
    """Cancel matching material, treating bishops and knights as minor pieces."""
    kinds = ('pawn', 'minor piece', 'rook', 'queen')
    left, right = dict(white_lost), dict(black_lost)
    for kind in kinds:
        common = min(left.get(kind, 0), right.get(kind, 0))
        left[kind] = left.get(kind, 0) - common
        right[kind] = right.get(kind, 0) - common
    if not any(left.values()) or not any(right.values()):
        return None
    if not any(left[k] or right[k] for k in kinds[1:]):
        return None

    def describe(items):
        return ' + '.join(f'{n} {kind}' + ('s' if n != 1 else '')
                          for kind in reversed(kinds) if (n := items.get(kind, 0)))
    return f'White gives {describe(left)} for {describe(right)}'


def material_imbalances(fen, pv, plies=12, min_ply=4):
    """Group capture sequences; report material trades, not their soundness."""
    board = chess.Board(fen)
    lost = {chess.WHITE: {}, chess.BLACK: {}}
    start = end = quiet = 0
    results = []

    def finish():
        if start >= min_ply:
            description = exchange_description(lost[chess.WHITE], lost[chess.BLACK])
            if description:
                results.append((end, f'Material imbalance · {description} · plies {start}–{end} (PV only)'))
        lost[chess.WHITE].clear()
        lost[chess.BLACK].clear()

    for ply, text in enumerate(pv[:plies], 1):
        move = board.parse_uci(text)
        victim = board.piece_at(move.to_square)
        if board.is_en_passant(move):
            victim = chess.Piece(chess.PAWN, not board.turn)
        if victim:
            if not start:
                start = ply
            kind = ('minor piece' if victim.piece_type in (chess.KNIGHT, chess.BISHOP)
                    else chess.piece_name(victim.piece_type))
            items = lost[victim.color]
            items[kind] = items.get(kind, 0) + 1
            end, quiet = ply, 0
        else:
            quiet += 1
        board.push(move)
        if start and quiet >= 2:
            finish()
            start = 0
        # Promotions change material independently of captures; don't confuse
        # that gain with compensation for a sacrificed piece.
        if move.promotion:
            lost[chess.WHITE].clear()
            lost[chess.BLACK].clear()
            start = 0
    if start:
        finish()
    return results


def tactic_patterns(fen, pv, plies=12, min_ply=4):
    """Conservative pattern hints, not engine proof of a sound combination."""
    board = chess.Board(fen)
    values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
              chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
    found = material_imbalances(fen, pv, plies, min_ply)
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
        self.fresh_checkpoints = set()
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
        self._buttons()

    def showEvent(self, event):
        super().showEvent(event)
        self._availability()
        self.poll.start()

    def hideEvent(self, event):
        self.poll.stop()
        self.cancel()
        super().hideEvent(event)

    def position(self, key, fen, turn):
        if self.key == key:
            return
        self.cancel()
        self.key = key
        self.root, self.turn = fen, turn
        self.session = None
        self.fresh_checkpoints.clear()
        self.live = {}
        self.checkpoints = self.records.setdefault(key, {})
        self.records.move_to_end(key)
        while len(self.records) > 128:
            self.records.popitem(last=False)
        self.next_nodes = max(self.checkpoints, default=500_000) * 2
        self.anchor = []
        self.select(None)

    def observe(self, session, lines, nodes):
        new_session = self.session != session
        if new_session:
            self.session = session
            self.fresh_checkpoints.clear()
            self.next_nodes = 1_000_000
            self.cancel()
            self._buttons()
        self.live = deepcopy(lines)
        if new_session and self.selected is not None:
            self._render()
        if self.mode.currentIndex() and not self.anchor:
            self.anchor = [x['pv'][0] for _, x in sorted(lines.items()) if x.get('pv')]
        crossed = None
        while nodes >= self.next_nodes:
            crossed = self.next_nodes
            self.next_nodes *= 2
        if crossed is not None:
            # A single output must never masquerade as multiple checkpoints.
            # live is replaced, not mutated, by subsequent output. Share this
            # detached copy with the checkpoint instead of copying every PV twice.
            self.checkpoints[crossed] = (nodes, self.live)
            self.fresh_checkpoints.add(crossed)
            self._buttons()
            if self.selected == crossed:
                self._render()
        if self.selected is None and self.mode.currentIndex():
            self._render()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _buttons(self):
        self._clear_layout(self.tabs_layout)
        for value in [None] + sorted(self.checkpoints):
            button = QPushButton('Live' if value is None else node_label(value))
            button.setCheckable(True)
            button.setChecked(self.selected == value)
            if value is not None:
                actual, lines = self.checkpoints[value]
                previous = value not in self.fresh_checkpoints
                origin = 'Previous run' if previous else 'Current run'
                button.setToolTip(f'{origin}: first captured output at {actual:,} nodes. {len(lines)} MultiPV lines; individual lines may have different depths.')
                button.setProperty('previousRun', previous)
                if previous:
                    button.setText(node_label(value) + ' •')
                    button.setStyleSheet('border: 1px dashed #b88735;')
                    button.setAccessibleName(node_label(value) + ', previous run')
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
        previous = self.selected is not None and self.selected not in self.fresh_checkpoints
        self.caption.setText('Viewing: ' + ('Live' if self.selected is None else node_label(self.selected))
                             + (' · previous run' if previous else ''))
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
