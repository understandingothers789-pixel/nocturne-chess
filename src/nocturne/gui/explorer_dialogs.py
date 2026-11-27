"""Filters and sample games for the Lichess opening databases."""

from dataclasses import replace

import chess
from PySide6.QtCore import QTimer, Qt, QUrl, QUrlQuery
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..core.game import Game
from ..explorer import GAME_ID, MAX_RESPONSE, RATINGS, rating_band, valid_explorer_month


def lichess_game_url(query, game_id, flipped=False):
    if query.source not in ("masters", "lichess") or not GAME_ID.fullmatch(game_id):
        raise ValueError("Invalid Lichess game")
    path = "import/master" if query.source == "masters" else "game"
    url = QUrl(f"https://lichess.org/{path}/{game_id}/{'black' if flipped else 'white'}")
    params = QUrlQuery()
    params.addQueryItem("fen", query.fen)
    url.setQuery(params)
    return url


class ExplorerFiltersDialog(QDialog):
    def __init__(self, source, since, until, rating, groups, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lichess explorer filters")
        self.resize(400, 0)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.first_month = QLineEdit(since)
        self.last_month = QLineEdit(until)
        self.first_month.setPlaceholderText("YYYY-MM or leave blank")
        self.last_month.setPlaceholderText("YYYY-MM or leave blank")
        self.first_month.setMaxLength(7)
        self.last_month.setMaxLength(7)
        form.addRow("From month", self.first_month)
        form.addRow("Through month", self.last_month)
        layout.addLayout(form)
        self.bands = {}
        if source == "lichess":
            ratings = QGroupBox("Rating bands")
            grid = QGridLayout(ratings)
            selected = groups or tuple(value for value in RATINGS if value >= rating)
            for index, value in enumerate(RATINGS):
                box = QCheckBox(rating_band(value))
                box.setChecked(value in selected)
                self.bands[value] = box
                grid.addWidget(box, index // 3, index % 3)
            layout.addWidget(ratings)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.hide()
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Reset
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(self._reset)
        layout.addWidget(buttons)

    def _reset(self):
        self.first_month.clear()
        self.last_month.clear()
        for box in self.bands.values():
            box.setChecked(True)
        self.message.hide()

    def accept(self):
        since, until = self.first_month.text().strip(), self.last_month.text().strip()
        groups = tuple(value for value, box in self.bands.items() if box.isChecked())
        if not valid_explorer_month(since) or not valid_explorer_month(until):
            message = "Enter months as YYYY-MM."
        elif since and until and since > until:
            message = "The first month must be on or before the last month."
        elif self.bands and not groups:
            message = "Select at least one rating band."
        else:
            self.values = since, until, () if groups == RATINGS else groups
            super().accept()
            return
        self.message.setText(message)
        self.message.show()


class ExplorerGamesDialog(QDialog):
    def __init__(self, client, query, parent=None, *, flipped=False):
        super().__init__(parent)
        self.client = client
        self.query = replace(query, include_games=True)
        self.game = None
        self.flipped = flipped
        self.change_filters = False
        self.samples = []
        self.rows = []
        self.reply = None
        self.setWindowTitle(f"Games from {query.label}")
        self.resize(800, 420)
        layout = QVBoxLayout(self)
        filters = [query.speed, query.rating_label] if query.source == "lichess" else []
        if query.date_label:
            filters.append(query.date_label)
        summary = QLabel(" · ".join(filters) if filters else "All dates")
        summary.setWordWrap(True)
        summary.setObjectName("muted")
        layout.addWidget(summary)
        filter_row = QHBoxLayout()
        self.move_filter = QComboBox()
        self.move_filter.setAccessibleName("Played move")
        self.list_filter = QComboBox()
        self.list_filter.setAccessibleName("Sample list")
        for combo, label in ((self.move_filter, "Move"), (self.list_filter, "List")):
            combo.addItem(f"All {label.lower()}s", "")
            filter_row.addWidget(QLabel(label))
            filter_row.addWidget(combo, 1)
            combo.currentIndexChanged.connect(self._render_rows)
        explorer_filters = QPushButton("Explorer filters…")
        explorer_filters.setToolTip("Change the date and rating filters used to fetch game samples.")
        explorer_filters.clicked.connect(self._edit_explorer_filters)
        explorer_filters.setVisible(parent is not None)
        filter_row.addWidget(explorer_filters)
        layout.addLayout(filter_row)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["List", "White", "Black", "Played", "Result", "Date"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        for index in range(6):
            self.table.horizontalHeader().setSectionResizeMode(
                index, QHeaderView.ResizeMode.Stretch if index in (1, 2) else QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAccessibleName("Lichess game samples")
        self.table.itemSelectionChanged.connect(self._sync_button)
        self.table.cellDoubleClicked.connect(self._open_game)
        layout.addWidget(self.table)
        self.status = QLabel("Loading game samples…")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.open_game = buttons.addButton("Open in new tab", QDialogButtonBox.ButtonRole.ActionRole)
        self.open_game.setEnabled(False)
        self.open_game.clicked.connect(self._open_game)
        self.open_lichess = buttons.addButton("View on Lichess ↗", QDialogButtonBox.ButtonRole.ActionRole)
        self.open_lichess.setToolTip("Open this game in your browser at the position being explored.")
        self.open_lichess.setEnabled(False)
        self.open_lichess.clicked.connect(self._view_on_lichess)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        client.result.connect(self._result)
        client.status.connect(self._status)
        self.finished.connect(self._cancel)

    def load(self):
        self.client.load(self.query)

    def _result(self, key, data, origin):
        if key != self.query.key:
            return
        samples = {}
        for name, games in (
            ("Top", data.get("topGames", [])), ("Recent", data.get("recentGames", [])),
            ("Example", [row["game"] for row in data["moves"] if "game" in row]),
        ):
            for game in games:
                sample = samples.setdefault(game["id"], ([], game))
                if name not in sample[0]:
                    sample[0].append(name)
        self.samples = list(samples.values())
        moves = dict(sorted({game["uci"]: game["san"] for _, game in self.samples}.items(), key=lambda pair: pair[1]))
        lists = {name for names, _ in self.samples for name in names}
        self._set_filter_choices(self.move_filter, "All moves", [(san, uci) for uci, san in moves.items()])
        self._set_filter_choices(
            self.list_filter, "All lists", [(name, name) for name in ("Top", "Recent", "Example") if name in lists]
        )
        self._render_rows()
        self._status(key, origin)

    @staticmethod
    def _set_filter_choices(combo, title, choices):
        selected = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(title, "")
        for text, value in choices:
            combo.addItem(text, value)
        combo.setCurrentIndex(max(0, combo.findData(selected)))
        combo.setEnabled(bool(choices))
        combo.blockSignals(False)

    def _render_rows(self):
        move, category = self.move_filter.currentData(), self.list_filter.currentData()
        selected = self._selected_sample()
        self.rows = [(names, game) for names, game in self.samples
                     if (not move or game["uci"] == move) and (not category or category in names)]
        self.table.setRowCount(len(self.rows))
        for index, (names, game) in enumerate(self.rows):
            players = [f"{p['name']} ({p['rating']})" if p["rating"] else p["name"]
                       for p in (game["white"], game["black"])]
            result = {"white": "1–0", "black": "0–1", None: "½–½"}[game["winner"]]
            date = game["month"] or str(game["year"] or "—")
            for column, value in enumerate((", ".join(names), *players, game["san"], result, date)):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(index, column, item)
        if self.rows:
            row = next((index for index, (_, game) in enumerate(self.rows) if game is selected), 0)
            self.table.selectRow(row)
        self._sync_button()

    def _status(self, key, message):
        if key != self.query.key or self.reply:
            return
        if message.startswith(("Live ·", "Cached ·")):
            message = (f"{len(self.samples)} game samples · {message}" if self.samples
                       else "Lichess returned no game samples for this position and filters.")
        self.status.setText(message)

    def _sync_button(self):
        selected = self._selected_sample() is not None
        self.open_game.setEnabled(self.reply is None and selected)
        self.open_lichess.setEnabled(selected)

    def _selected_sample(self):
        row = self.table.currentRow()
        return self.rows[row][1] if 0 <= row < len(self.rows) else None

    def _view_on_lichess(self):
        if (sample := self._selected_sample()) and not QDesktopServices.openUrl(
            lichess_game_url(self.query, sample["id"], self.flipped)
        ):
            self.status.setText("Could not open the default browser.")

    def _edit_explorer_filters(self):
        self.change_filters = True
        self.reject()

    def _open_game(self, *_):
        sample = self._selected_sample()
        if self.reply or not sample:
            return
        request = self.client.game_request(self.query.source, sample["id"])
        reply = self.reply = self.client.network.get(request)
        body = bytearray()

        def read():
            body.extend(reply.read(MAX_RESPONSE + 1 - len(body)))
            if len(body) > MAX_RESPONSE:
                reply.abort()

        reply.readyRead.connect(read)
        reply.finished.connect(lambda: self._finish_game(reply, body, sample))
        QTimer.singleShot(10_000, self, lambda: reply.abort() if reply is self.reply else None)
        self._sync_button()
        self.status.setText("Loading game PGN…")

    def _finish_game(self, reply, body, sample):
        reply.deleteLater()
        if reply is not self.reply:
            return
        self.reply = None
        self._sync_button()
        body.extend(reply.read(MAX_RESPONSE + 1 - len(body)))
        if len(body) > MAX_RESPONSE:
            self.status.setText("This game exceeds the PGN download limit.")
            return
        code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if reply.error() != QNetworkReply.NetworkError.NoError or code != 200:
            self.status.setText(f"Lichess could not return this game (HTTP {code})." if code
                                else "Lichess could not return this game. Check your connection.")
            return
        try:
            text = body.decode("utf-8-sig")
            if not text.lstrip().startswith("["):
                raise ValueError("Missing PGN headers")
            game = Game.from_pgn(text)
            if not game.moves:
                raise ValueError("No game moves found")
            self._select_position(game, sample)
        except (UnicodeError, ValueError):
            self.status.setText("Lichess returned an unreadable game PGN.")
            return
        self.game = game
        self.accept()

    def _select_position(self, game, sample):
        target = self.query.fen.split()[:4]
        board = chess.Board(game.initial_fen)
        first = None
        for ply, move in enumerate(game.moves):
            if board.fen(en_passant="legal").split()[:4] == target:
                if move.uci() == sample["uci"]:
                    game.navigate(ply)
                    return
                if first is None:
                    first = ply
            board.push_uci(move.uci())
        game.navigate(first or 0)

    def _cancel(self, _):
        if self.client.query == self.query:
            self.client.cancel()
        reply, self.reply = self.reply, None
        if reply:
            reply.abort()
