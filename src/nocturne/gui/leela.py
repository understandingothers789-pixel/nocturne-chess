"""Optional Lc0 WDL analysis and asynchronous Windows DirectML setup."""
from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import urllib.request
import zipfile

from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel,
                              QSpinBox, QComboBox, QPushButton, QTableWidget,
                              QTableWidgetItem, QHeaderView)
from .engine import EngineController
from ..engine.uci_types import AnalysisLimits

NETWORK = 'https://storage.lczero.org/files/networks-contrib/BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz'


class LeelaInstaller(QThread):
    status = Signal(str)
    ready = Signal(str, str)
    failed = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)

    def download(self, url, target, digest=None):
        temporary = target.with_suffix(target.suffix + '.part')
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Nocturne-Chess'})
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as out:
                checksum = hashlib.sha256()
                total = int(response.headers.get('Content-Length', 0))
                count = 0
                while chunk := response.read(1024 * 1024):
                    if self.isInterruptionRequested():
                        raise RuntimeError('Setup cancelled')
                    out.write(chunk)
                    checksum.update(chunk)
                    count += len(chunk)
                    self.status.emit(f'Downloading {target.name}: {count // 1048576} MB' +
                                     (f' / {total // 1048576} MB' if total else ''))
            if digest and checksum.hexdigest() != digest.removeprefix('sha256:'):
                raise RuntimeError('Download checksum mismatch')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    def run(self):
        try:
            if os.name != 'nt':
                raise RuntimeError('Automatic Leela DirectML setup requires Windows x64.')
            self.root.mkdir(parents=True, exist_ok=True)
            manifest = self.root / 'installed.json'
            if not manifest.exists():
                self.status.emit('Finding latest stable Lc0 release…')
                request = urllib.request.Request(
                    'https://api.github.com/repos/LeelaChessZero/lc0/releases/latest',
                    headers={'User-Agent': 'Nocturne-Chess'})
                with urllib.request.urlopen(request, timeout=30) as response:
                    release = json.load(response)
                asset = next(a for a in release['assets'] if a['name'].endswith('windows-onnx-dml.zip'))
                archive = self.root / 'lc0.zip'
                self.download(asset['browser_download_url'], archive, asset.get('digest'))
                with zipfile.ZipFile(archive) as source:
                    for member in source.infolist():
                        dest = (self.root / member.filename).resolve()
                        if not dest.is_relative_to(self.root.resolve()):
                            raise RuntimeError('Invalid archive path')
                    source.extractall(self.root)
                archive.unlink()
                runtime = self.root / 'directml.zip'
                self.download('https://www.nuget.org/api/v2/package/Microsoft.AI.DirectML/1.15.4', runtime)
                with zipfile.ZipFile(runtime) as source:
                    (self.root / 'DirectML.dll').write_bytes(source.read('bin/x64-win/DirectML.dll'))
                    for name in source.namelist():
                        if name.lower().endswith('license.txt'):
                            (self.root / 'DirectML-LICENSE.txt').write_bytes(source.read(name))
                runtime.unlink()
                weights = self.root / 'BT4-it332.pb.gz'
                if not weights.exists():
                    self.download(NETWORK, weights)
                manifest.write_text(json.dumps({'version': release['tag_name'], 'network': NETWORK}), encoding='utf-8')
            exe = next(self.root.rglob('lc0.exe'))
            weights = self.root / 'BT4-it332.pb.gz'
            if not weights.exists() or not (self.root / 'DirectML.dll').exists():
                manifest.unlink(missing_ok=True)
                raise RuntimeError('Incomplete setup. Click Retry setup to repair it.')
            self.ready.emit(str(exe), str(weights))
        except Exception as exc:
            self.failed.emit(str(exc))


class LeelaPanel(QWidget):
    settings_changed = Signal()
    move_selected = Signal(str)
    results_changed = Signal(object)

    def __init__(self, root, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.root = Path(root) / 'leela'
        self.identity = None
        self.game = None
        self.active = False
        self.exe = self.weights = ''
        self.cache = OrderedDict()
        self.engine = EngineController(self)
        self.engine.connection.timeout_ms = 120000
        self.engine.message.connect(self._message)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(200)
        self.render_timer.timeout.connect(self._render)
        self.engine.status.connect(self._status)
        self.installer = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._start)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Leela · WDL contempt'))
        self.status = QLabel('Enable Leela to set up GPU analysis')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        details = QPushButton('Details · rating assumptions')
        details.setCheckable(True)
        layout.addWidget(details)
        settings = QWidget()
        form = QFormLayout(settings)
        self.side = QComboBox()
        self.side.addItems(['White', 'Black'])
        self.side.setCurrentIndex(0 if config['leela_side'] == 'white' else 1)
        self.rating, self.opponent, self.gap = QSpinBox(), QSpinBox(), QSpinBox()
        self.rating.setRange(800, 3500)
        self.opponent.setRange(400, 3500)
        self.gap.setRange(-2000, 2000)
        self.rating.setValue(config['leela_rating'])
        self.gap.setValue(config['leela_gap'])
        self.opponent.setValue(config['leela_rating'] - config['leela_gap'])
        form.addRow('Perspective / stronger side', self.side)
        form.addRow('Selected side rating', self.rating)
        form.addRow('Opponent rating', self.opponent)
        form.addRow('Rating advantage (+ = stronger)', self.gap)
        self.seconds = QSpinBox()
        self.seconds.setRange(1, 120)
        self.seconds.setValue(config['leela_seconds'])
        self.device = QSpinBox()
        self.device.setRange(0, 16)
        self.device.setValue(config['leela_device'])
        form.addRow('Seconds per position', self.seconds)
        form.addRow('DirectML GPU index', self.device)
        layout.addWidget(settings)
        settings.hide()
        details.toggled.connect(settings.setVisible)
        self.side.currentIndexChanged.connect(self._settings)
        self.rating.valueChanged.connect(self._settings)
        self.gap.valueChanged.connect(self._settings)
        self.opponent.valueChanged.connect(lambda: self._settings(opponent=True))
        self.seconds.valueChanged.connect(self._settings)
        self.device.valueChanged.connect(self._settings)
        self.outcome = QLabel('Win —    Draw —    Loss —')
        self.outcome.setWordWrap(True)
        layout.addWidget(self.outcome)
        note = QLabel('Model estimates for the selected side and matchup; not human move probabilities.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Move', 'W / D / L', 'Variation'])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellClicked.connect(self._clicked)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        retry = QPushButton('Retry setup')
        retry.clicked.connect(self.setup)
        row.addWidget(retry)
        restart = QPushButton('Analyze again')
        restart.clicked.connect(lambda: self.request(self.game, force=True) if self.game else None)
        row.addWidget(restart)
        layout.addLayout(row)
        self.lines = {}

    def _settings(self, *args, opponent=False):
        if opponent:
            gap = self.rating.value() - self.opponent.value()
            self.gap.blockSignals(True)
            self.gap.setValue(gap)
            self.gap.blockSignals(False)
        else:
            self.opponent.blockSignals(True)
            self.opponent.setValue(self.rating.value() - self.gap.value())
            self.opponent.blockSignals(False)
        self.config.update(leela_side=self.side.currentText().lower(), leela_rating=self.rating.value(),
                           leela_gap=self.gap.value(), leela_seconds=self.seconds.value(),
                           leela_device=self.device.value())
        self.identity = None
        self.settings_changed.emit()
        if self.game and self.active:
            self.request(self.game)

    def _status(self, text):
        self.status.setText(text)

    def setup(self):
        if self.installer and self.installer.isRunning():
            return
        self.installer = LeelaInstaller(self.root, self)
        self.installer.status.connect(self._status)
        self.installer.failed.connect(lambda text: self._status('Leela setup failed: ' + text))
        self.installer.ready.connect(self._ready)
        self.installer.start()

    def _ready(self, exe, weights):
        self.exe, self.weights = exe, weights
        if self.active:
            self.timer.start()

    def request(self, game, force=False):
        if not self.active:
            return
        self.game = game
        key = (game.board.fen(), tuple(m.uci() for m in game.moves[:game.cursor]),
               self.config['leela_side'], self.config['leela_rating'], self.config['leela_gap'],
               self.config['leela_seconds'], self.config['leela_device'])
        if key == self.identity and not force:
            return
        self.engine.stop()
        self.render_timer.stop()
        self.identity = key
        self.lines = {}
        self.table.setRowCount(0)
        self.outcome.setText('Win —    Draw —    Loss —')
        self.results_changed.emit({})
        if key in self.cache and not force:
            self.lines = dict(self.cache[key])
            self._render()
            self._status('Leela · cached WDL analysis')
            return
        self._status('Leela · waiting to analyze…')
        self.timer.start()

    def _start(self):
        if not self.active or not self.game:
            return
        if not self.exe:
            self.setup()
            return
        cfg = self.config
        options = {'Backend': 'onnx-dml', 'WeightsFile': self.weights,
                   'BackendOptions': f'gpu={cfg["leela_device"]}', 'UCI_ShowWDL': True,
                   'ContemptMode': cfg['leela_side'] + '_side_analysis',
                   'WDLCalibrationElo': str(cfg['leela_rating']), 'Contempt': str(cfg['leela_gap']),
                   'WDLEvalObjectivity': '0.0', 'WDLContemptAttenuation': '1.0',
                   'WDLDrawRateReference': '0.62', 'MovesLeftThreshold': '0.95',
                   'Threads': 2, 'NNCacheSize': 200000}
        try:
            self.engine.start(self.game, AnalysisLimits(depth=128, seconds=cfg['leela_seconds']),
                              external=self.exe, kind='analysis', multipv=5, options=options,
                              arguments=['--backend=onnx-dml', '--minibatch-size=16', '--weights=' + self.weights])
            self._status('Leela · DirectML GPU analysis')
        except (ValueError, OSError) as exc:
            self._status('Leela: ' + str(exc))

    def _message(self, generation, kind, info):
        if not self.active:
            return
        if kind == 'info':
            self.lines[info['multipv']] = info
            if not self.render_timer.isActive():
                self.render_timer.start()
        elif kind == 'error':
            self._status('Leela: ' + info.get('message', 'Engine error'))
        elif kind == 'result':
            self.render_timer.stop()
            self._render()
            self._status('Leela · analysis complete')

    def _wdl(self, info):
        values = info.get('wdl')
        if values and self.game.board.turn != (1 if self.config['leela_side'] == 'white' else -1):
            values = values[::-1]
        return values

    def _render(self):
        if not self.active or self.identity is None:
            return
        self.table.setRowCount(len(self.lines))
        for row, rank in enumerate(sorted(self.lines)):
            info = self.lines[rank]
            wdl = self._wdl(info)
            text = ' / '.join(f'{n / 10:.1f}%' for n in wdl) if wdl else 'Awaiting WDL'
            for column, value in enumerate([info['san'][0], text, ' '.join(info['san'])]):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, info['pv'][0])
                self.table.setItem(row, column, item)
            if rank == 1 and wdl:
                self.outcome.setText(f'{self.config["leela_side"].title()}: Win {wdl[0]/10:.1f}%   Draw {wdl[1]/10:.1f}%   Loss {wdl[2]/10:.1f}%')
        self.cache[self.identity] = dict(self.lines)
        self.cache.move_to_end(self.identity)
        while len(self.cache) > 128:
            self.cache.popitem(last=False)
        self.results_changed.emit(self.lines)

    def _clicked(self, row, column):
        item = self.table.item(row, column)
        if item:
            self.move_selected.emit(item.data(Qt.ItemDataRole.UserRole))

    def stop(self):
        self.active = False
        self.identity = None
        self.timer.stop()
        self.render_timer.stop()
        self.engine.stop()

    def shutdown(self):
        self.stop()
        self.engine.connection.close()
        if self.installer and self.installer.isRunning():
            self.installer.requestInterruption()
            self.installer.wait(65000)
