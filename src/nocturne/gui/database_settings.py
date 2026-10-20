"""Validated filters matching the Masters, Lichess and player explorer APIs."""

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QGridLayout, QGroupBox, QLabel, QLineEdit, QVBoxLayout,
)

from ..core.board import START_FEN
from ..explorer import ExplorerQuery, RATINGS, SPEEDS
from ..settings import DEFAULTS


class DatabaseSettings(QDialog):
    def __init__(self, config, parent=None, source=None):
        super().__init__(parent)
        self.setWindowTitle("Database settings and filters")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.source = QComboBox()
        for title, key in (("Lichess Masters database", "masters"), ("Lichess", "lichess"),
                           ("Player", "player"), ("ChessDB Cloud Analysis", "chessdb")):
            self.source.addItem(title, key)
        form.addRow("Database", self.source)
        self.player = QLineEdit()
        self.player.setPlaceholderText("Lichess username")
        self.color = QComboBox()
        self.color.addItems(["White", "Black"])
        form.addRow("Player", self.player)
        form.addRow("Player's pieces", self.color)
        layout.addLayout(form)
        self.speeds = {}
        speed_box = QGroupBox("Time control · include selected groups")
        grid = QGridLayout(speed_box)
        for i, value in enumerate(SPEEDS):
            check = QCheckBox(value[0].upper()+value[1:])
            self.speeds[value] = check
            grid.addWidget(check, i//3, i%3)
        layout.addWidget(speed_box)
        self.ratings = {}
        rating_box = QGroupBox("Lichess rating bands · include selected groups")
        grid = QGridLayout(rating_box)
        for i, value in enumerate(RATINGS):
            end = RATINGS[i+1]-1 if i+1 < len(RATINGS) else None
            title = f"{value}–{end}" if end is not None else f"{value}+"
            check = QCheckBox(title)
            self.ratings[value] = check
            grid.addWidget(check, i//3, i%3)
        layout.addWidget(rating_box)
        self.speed_box, self.rating_box = speed_box, rating_box
        dates = QFormLayout()
        self.since_on, self.until_on = QCheckBox("Since"), QCheckBox("Until")
        self.since, self.until = QDateEdit(), QDateEdit()
        for check, field in ((self.since_on, self.since), (self.until_on, self.until)):
            field.setCalendarPopup(True)
            field.setDateRange(QDate(1600, 1, 1), QDate(3000, 12, 31))
            check.toggled.connect(self._sync)
            dates.addRow(check, field)
        layout.addLayout(dates)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.error = QLabel()
        self.error.setStyleSheet("color:#dc9183;")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply |
                                       QDialogButtonBox.StandardButton.Cancel |
                                       QDialogButtonBox.StandardButton.RestoreDefaults)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setText("Apply / Done")
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            lambda: self._fill(DEFAULTS))
        layout.addWidget(self.buttons)
        self.source.currentIndexChanged.connect(self._sync)
        self._fill(config)
        if source is not None:
            self.source.setCurrentIndex(self.source.findData(source))

    def _fill(self, config):
        self.source.setCurrentIndex(max(0, self.source.findData(config.get("explorer_source", "chessdb"))))
        self.player.setText(config.get("explorer_player", ""))
        self.color.setCurrentIndex(1 if config.get("explorer_color") == "black" else 0)
        selected = config.get("explorer_speeds") or (SPEEDS if config.get("explorer_speed", "all") == "all"
                                                    else [config["explorer_speed"]])
        for value, check in self.speeds.items():
            check.setChecked(value in selected)
        selected = config.get("explorer_ratings") or [r for r in RATINGS if r >= config.get("explorer_rating", 0)]
        for value, check in self.ratings.items():
            check.setChecked(value in selected)
        for key, check, field in (("since", self.since_on, self.since), ("until", self.until_on, self.until)):
            text = config.get("explorer_"+key, "")
            date = QDate.fromString(text if len(text) == 7 else text+"-01", "yyyy-MM")
            field.setDate(date if date.isValid() else QDate.currentDate())
            check.setChecked(bool(text))
        self.error.clear()
        self._sync()

    def _sync(self):
        source = self.source.currentData()
        self.player.setEnabled(source == "player")
        self.color.setEnabled(source == "player")
        self.speed_box.setEnabled(source in ("lichess", "player"))
        self.rating_box.setEnabled(source == "lichess")
        for check, field in ((self.since_on, self.since), (self.until_on, self.until)):
            check.setEnabled(source != "chessdb")
            field.setEnabled(source != "chessdb" and check.isChecked())
            field.setDisplayFormat("yyyy" if source == "masters" else "yyyy-MM")
        self.note.setText("Masters filters use years. Lichess and Player use months. Player statistics may "
                          "take time to index; provisional results are labelled. ChessDB supplies cloud scores "
                          "and has no game-count, date or rating filters.")

    def values(self):
        source = self.source.currentData()
        speeds = [v for v, check in self.speeds.items() if check.isChecked()]
        ratings = [v for v, check in self.ratings.items() if check.isChecked()]
        date_format = "yyyy" if source == "masters" else "yyyy-MM"
        return dict(explorer_source=source, explorer_speed="all", explorer_rating=0,
                    explorer_speeds=[] if tuple(speeds) == SPEEDS else speeds,
                    explorer_ratings=[] if tuple(ratings) == RATINGS else ratings,
                    explorer_since=self.since.date().toString(date_format) if self.since_on.isChecked() else "",
                    explorer_until=self.until.date().toString(date_format) if self.until_on.isChecked() else "",
                    explorer_player=self.player.text().strip(),
                    explorer_color="black" if self.color.currentIndex() else "white")

    def _accept(self):
        values = self.values()
        source = values["explorer_source"]
        if source in ("lichess", "player") and not any(c.isChecked() for c in self.speeds.values()):
            self.error.setText("Select at least one time control.")
            return
        if source == "lichess" and not any(c.isChecked() for c in self.ratings.values()):
            self.error.setText("Select at least one rating band.")
            return
        try:
            ExplorerQuery(START_FEN, source, speeds=values["explorer_speeds"], ratings=values["explorer_ratings"],
                          since=values["explorer_since"], until=values["explorer_until"],
                          player=values["explorer_player"], color=values["explorer_color"])
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()
