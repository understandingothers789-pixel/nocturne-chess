"""Compare immutable analysis checkpoints for one saved PGN position."""

from html import escape

from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
)

from ..engine.uci_types import score_label
from ..snapshots import node_label
from .theme import palette


class SnapshotDialog(QDialog):
    def __init__(self, load_records, light=False, parent=None):
        super().__init__(parent)
        self.load_records = load_records
        self.colors = palette(light)
        self.setWindowTitle("Compare saved analysis snapshots")
        self.resize(1100, 620)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Same PGN position · evaluations favor White · each PV retains its actual depth"))
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        columns = QHBoxLayout()
        self.selectors, self.views = [], []
        for _ in range(2):
            column = QVBoxLayout()
            selector = QComboBox()
            selector.currentIndexChanged.connect(self._render)
            self.selectors.append(selector)
            column.addWidget(selector)
            view = QTextBrowser()
            view.setOpenExternalLinks(False)
            self.views.append(view)
            column.addWidget(view, 1)
            columns.addLayout(column, 1)
        layout.addLayout(columns, 1)
        controls = QHBoxLayout()
        refresh = QPushButton("Refresh saved checkpoints")
        refresh.clicked.connect(self.reload)
        controls.addWidget(refresh)
        controls.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        controls.addWidget(close)
        layout.addLayout(controls)
        self.records = []
        self.reload()

    def reload(self):
        previous = [selector.currentData() for selector in self.selectors]
        self.records = self.load_records()
        for side, selector in enumerate(self.selectors):
            selector.blockSignals(True)
            selector.clear()
            for record in self.records:
                label = f"{node_label(record['milestone'])} checkpoint · {node_label(record['observed_nodes'])} reported"
                selector.addItem(label, record["milestone"])
            selected = selector.findData(previous[side])
            selector.setCurrentIndex(selected if selected >= 0 else (0 if side == 0 else len(self.records) - 1))
            selector.blockSignals(False)
        self._render()

    def _render(self):
        if len(self.views) != 2:
            return
        chosen = []
        for selector, view in zip(self.selectors, self.views):
            index = selector.currentIndex()
            record = self.records[index] if 0 <= index < len(self.records) else None
            chosen.append(record)
            if record is None:
                view.setPlainText("No snapshots saved for this position. Enable Dev → Save analysis snapshots at node milestones, then start analysis.")
                continue
            lines = record["lines"]
            header = (f"<p>{escape(record.get('timestamp', ''))}<br>"
                      f"Engine: {escape(lines[0].get('engine', record.get('profile', 'UCI')))}<br>"
                      f"PVs available: {len(lines)}/{record.get('requested_multipv', len(lines))}<br>"
                      f"Target: {record['milestone']:,} nodes · reported: {record['observed_nodes']:,}</p>")
            parts = [header]
            for info in lines:
                score = escape(score_label(info, record["turn"]))
                depth = info.get("depth", "?")
                pv = escape("  ".join(info.get("san", [])))
                parts.append(
                    f'<p><span style="color:{self.colors["metric"]};font-size:18px">{score}</span>'
                    f' <span>Depth {depth}</span><br>'
                    f'<span style="font-family:monospace;font-size:14px">{pv}</span><br>'
                    f'<small>{info.get("nodes", 0):,} nodes · {escape(info.get("bound", "exact"))}</small></p>'
                )
            view.setHtml("".join(parts))
        if all(chosen):
            old = {line["multipv"]: line for line in chosen[0]["lines"]}
            changes = []
            for line in chosen[1]["lines"]:
                earlier = old.get(line["multipv"])
                if earlier and earlier.get("san") and line.get("san"):
                    changes.append(f"{earlier['san'][0]} {score_label(earlier, chosen[0]['turn'])} → "
                                   f"{line['san'][0]} {score_label(line, chosen[1]['turn'])}")
            self.summary.setText("  ·  ".join(changes))
        else:
            self.summary.setText("Checkpoints use the first engine report reaching each target; reported nodes may exceed the target.")
