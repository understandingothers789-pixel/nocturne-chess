"""Optional Lc0 WDL analysis and asynchronous Windows DirectML setup."""
from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import urllib.request
import zipfile

from PySide6.QtCore import QThread, QTimer, Signal, QPoint
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel,
                              QSpinBox, QComboBox, QPushButton, QCheckBox)
from .engine import EngineController
from ..engine.uci_types import AnalysisLimits, score_label
from .moves import MoveText
from .theme import palette
from .leela_gpu import directml_adapters, preferred_adapter
from PySide6.QtWidgets import QApplication

NETWORK = 'https://storage.lczero.org/files/networks-contrib/BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz'


class LeelaInstaller(QThread):
    status = Signal(str)
    ready = Signal(str, str, object)
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
            self.status.emit('Detecting DirectML GPU adapters…')
            try:
                gpu_info = dict(adapters=directml_adapters(), error='')
            except (OSError, ValueError, AttributeError) as exc:
                gpu_info = dict(adapters=[], error=str(exc))
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
            self.ready.emit(str(exe), str(weights), gpu_info)
        except Exception as exc:
            self.failed.emit(str(exc))


class LeelaPanel(QWidget):
    settings_changed = Signal()
    move_selected = Signal(str)
    results_changed = Signal(object)
    preview = Signal(object, int)
    preview_end = Signal()
    pointer_moved = Signal(QPoint)
    line_selected = Signal(object)

    def __init__(self, root, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.root = Path(root) / 'leela'
        self.identity = None
        self.game = None
        self.active = False
        self.exe = self.weights = ''
        self.cache = OrderedDict()
        self.completed_cache = set()
        self.adapters = []
        self.gpu_error = ""
        self._launched_device = None
        self._launched_batch = None
        self.engine = EngineController(self)
        self.engine.connection.timeout_ms = 120000
        self.engine.message.connect(self._message)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(200)
        self.render_timer.timeout.connect(self._render)
        self.engine.status.connect(self._status)
        self.engine.discovered.connect(self._verify_engine)
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
        details = QPushButton('Advanced · ratings, GPU and search limits')
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
        side_row = QHBoxLayout()
        side_row.addWidget(self.side, 1)
        switch_side = QPushButton('⇄ Switch')
        switch_side.setToolTip('Switch White and Black, keeping the ratings and advantage.')
        switch_side.clicked.connect(lambda: self.side.setCurrentIndex(1 - self.side.currentIndex()))
        side_row.addWidget(switch_side)
        form.addRow('Perspective / stronger side', side_row)
        form.addRow('Selected side rating', self.rating)
        form.addRow('Opponent rating', self.opponent)
        form.addRow('Rating advantage (+ = stronger)', self.gap)
        self.seconds = QSpinBox()
        self.seconds.setRange(1, 120)
        self.seconds.setValue(config['leela_seconds'])
        self.time_enabled = QCheckBox('Enabled')
        self.nodes_enabled = QCheckBox('Enabled')
        self.time_enabled.setChecked(config['leela_limit'] in ('time', 'both'))
        self.nodes_enabled.setChecked(config['leela_limit'] in ('nodes', 'both'))
        self.nodes = QSpinBox()
        self.nodes.setRange(1, 2000000000)
        self.nodes.setGroupSeparatorShown(True)
        self.nodes.setValue(config['leela_nodes'])
        self.auto_gpu = QCheckBox('Automatically select discrete GPU (prefer Radeon)')
        self.auto_gpu.setChecked(config['leela_gpu_auto'])
        self.gpu_info = QLabel('Backend: ONNX DirectML GPU · adapter detected when Leela starts')
        self.gpu_info.setWordWrap(True)
        self.device = QSpinBox()
        self.device.setRange(0, 31)
        self.device.setValue(config['leela_device'])
        time_row = QHBoxLayout()
        time_row.addWidget(self.seconds, 1)
        time_row.addWidget(self.time_enabled)
        node_row = QHBoxLayout()
        node_row.addWidget(self.nodes, 1)
        node_row.addWidget(self.nodes_enabled)
        form.addRow('Maximum seconds', time_row)
        form.addRow('Maximum nodes', node_row)
        limit_note = QLabel('When both are enabled, the first limit reached stops the search. Disable both for unlimited analysis.')
        limit_note.setWordWrap(True)
        form.addRow(limit_note)
        self.batch = QSpinBox()
        self.batch.setRange(1, 512)
        self.batch.setValue(config['leela_batch_size'])
        self.batch.setToolTip('Larger batches may improve GPU throughput but use more VRAM and can affect search efficiency. Default: 16.')
        form.addRow('GPU batch size', self.batch)
        form.addRow(self.auto_gpu)
        form.addRow('GPU backend / adapter', self.gpu_info)
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
        self.time_enabled.toggled.connect(self._settings)
        self.nodes_enabled.toggled.connect(self._settings)
        self.batch.valueChanged.connect(self._settings)
        self.nodes.valueChanged.connect(self._settings)
        self.auto_gpu.toggled.connect(self._settings)
        self._sync_limit_controls()
        self.outcome = QLabel('Win —    Draw —    Loss —')
        self.outcome.setWordWrap(True)
        layout.addWidget(self.outcome)
        note = QLabel('Model estimates for the selected side and matchup; not human move probabilities.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.telemetry = QLabel('Depth — · Nodes —')
        layout.addWidget(self.telemetry)
        self.variations = QVBoxLayout()
        self.variations.setSpacing(0)
        self.rows = {}
        layout.addLayout(self.variations)
        layout.addStretch(1)
        self.leave_timer = QTimer(self)
        self.leave_timer.setSingleShot(True)
        self.leave_timer.setInterval(140)
        self.leave_timer.timeout.connect(self.preview_end)
        row = QHBoxLayout()
        retry = QPushButton('Retry setup')
        retry.clicked.connect(self.setup)
        row.addWidget(retry)
        restart = QPushButton('Analyze again')
        restart.clicked.connect(lambda: self.request(self.game, force=True) if self.game else None)
        row.addWidget(restart)
        layout.addLayout(row)
        self.lines = {}

    def _sync_limit_controls(self):
        self.seconds.setEnabled(self.time_enabled.isChecked())
        self.nodes.setEnabled(self.nodes_enabled.isChecked())
        self.device.setEnabled(not self.auto_gpu.isChecked())

    def _sync_gpu(self, active=False):
        selected = next((item for item in self.adapters if item['index'] == self.device.value()), None)
        if selected:
            name = f"{selected['name']} · {selected['memory_mb']:,} MB dedicated VRAM"
        else:
            name = 'Adapter name unavailable' + (': ' + self.gpu_error if self.gpu_error else '')
        prefix = 'Active' if active else 'Configured'
        text = f'{prefix}: ONNX DirectML GPU · index {self.device.value()}\n{name}'
        if self.gpu_info.text() != text:
            self.gpu_info.setText(text)
        self.gpu_info.setToolTip('DXGI adapter indices match the DirectML device setting. No CPU backend fallback is configured.')

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
        self.gap.blockSignals(True)
        self.gap.setRange(max(-2000, self.rating.value() - 3500), min(2000, self.rating.value() - 400))
        self.gap.blockSignals(False)
        self.opponent.blockSignals(True)
        self.opponent.setValue(self.rating.value() - self.gap.value())
        self.opponent.blockSignals(False)
        if self.auto_gpu.isChecked():
            selected = preferred_adapter(self.adapters)
            if selected:
                self.device.blockSignals(True)
                self.device.setValue(selected['index'])
                self.device.blockSignals(False)
        self._sync_limit_controls()
        self._sync_gpu()
        mode = ('both' if self.time_enabled.isChecked() and self.nodes_enabled.isChecked() else
                'time' if self.time_enabled.isChecked() else 'nodes' if self.nodes_enabled.isChecked() else 'infinite')
        self.config.update(leela_limit=mode, leela_nodes=self.nodes.value(), leela_batch_size=self.batch.value(),
                           leela_gpu_auto=self.auto_gpu.isChecked(), leela_side=self.side.currentText().lower(), leela_rating=self.rating.value(),
                           leela_gap=self.gap.value(), leela_seconds=self.seconds.value(),
                           leela_device=self.device.value())
        self.identity = None
        self.settings_changed.emit()
        if self.game and self.active:
            self.request(self.game)

    def _verify_engine(self, profile):
        required = {'ContemptMode', 'Contempt', 'WDLCalibrationElo', 'UCI_ShowWDL'}
        missing = required.difference(profile.get('options', {}))
        if missing:
            self.engine.stop()
            self._status('Lc0 is missing required WDL options: ' + ', '.join(sorted(missing)))

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

    def _ready(self, exe, weights, gpu_info=None):
        self.exe, self.weights = exe, weights
        gpu_info = gpu_info or {}
        self.adapters = gpu_info.get('adapters', [])
        self.gpu_error = gpu_info.get('error', '')
        self._settings()

    def request(self, game, force=False):
        if not self.active:
            return
        self.game = game
        key = (game.board.fen(), tuple(m.uci() for m in game.moves[:game.cursor]),
               self.config['leela_side'], self.config['leela_rating'], self.config['leela_gap'],
               self.config['leela_seconds'], self.config['leela_device'],
               self.config['leela_limit'], self.config['leela_nodes'], self.config['leela_gpu_auto'],
               self.config['leela_batch_size'])
        if key == self.identity and not force:
            return
        self._sync_gpu()
        self.engine.stop()
        self.render_timer.stop()
        self.identity = key
        self.lines = {}
        self.preview_end.emit()
        for moves, badge, frame in self.rows.values():
            frame.hide()
        self.telemetry.setText("Depth — · Nodes —")
        self.outcome.setText('Win —    Draw —    Loss —')
        self.results_changed.emit({})
        if key in self.cache and key in self.completed_cache and not force and self.config['leela_limit'] != 'infinite':
            self.lines = dict(self.cache[key])
            self._render()
            self._status('Leela · cached WDL analysis')
            return
        self.completed_cache.discard(key)
        self._status('Leela · waiting to analyze…')
        self.timer.start()

    def _start(self):
        if not self.active or not self.game:
            return
        if not self.exe:
            self.setup()
            return
        cfg = self.config
        if cfg['leela_gpu_auto'] and preferred_adapter(self.adapters) is None:
            self._status('GPU detection failed. In Advanced, disable automatic selection and choose an adapter index manually.')
            return
        selected = next((item for item in self.adapters if item['index'] == cfg['leela_device']), None)
        if selected and selected.get('software'):
            self._status('The selected adapter is a software renderer. Choose a hardware GPU.')
            return
        self._sync_gpu()
        if (self._launched_device, self._launched_batch) != (cfg['leela_device'], cfg['leela_batch_size']):
            self.engine.close()
            self._launched_device = cfg['leela_device']
            self._launched_batch = cfg['leela_batch_size']
        options = {'Backend': 'onnx-dml', 'WeightsFile': self.weights,
                   'BackendOptions': f'gpu={cfg["leela_device"]}', 'UCI_ShowWDL': True,
                   'ScoreType': 'centipawn',
                   'ContemptMode': cfg['leela_side'] + '_side_analysis',
                   'WDLCalibrationElo': str(cfg['leela_rating']), 'Contempt': str(cfg['leela_gap']),
                   'ContemptMaxValue': '2000.0',
                   'WDLEvalObjectivity': '0.0', 'WDLContemptAttenuation': '1.0',
                   'WDLDrawRateReference': '0.62', 'MovesLeftThreshold': '0.95',
                   'Threads': 2, 'NNCacheSize': 200000,
                   'MinibatchSize': cfg['leela_batch_size']}
        try:
            self.engine.start(self.game, AnalysisLimits(depth=128, seconds=cfg['leela_seconds'],
                                                         nodes=cfg['leela_nodes'] if cfg['leela_limit'] in ('nodes', 'both') else None),
                              external=self.exe, kind='analysis', multipv=5, options=options,
                              infinite=cfg['leela_limit'] == 'infinite',
                              nodes_only=cfg['leela_limit'] == 'nodes',
                              time_nodes_only=True,
                              arguments=['--backend=onnx-dml', f'--backend-opts=gpu={cfg["leela_device"]}',
                                         f'--minibatch-size={cfg["leela_batch_size"]}', '--weights=' + self.weights])
            self._status('Leela · DirectML GPU analysis')
        except (ValueError, OSError) as exc:
            self._status('Leela: ' + str(exc))

    def _message(self, generation, kind, info):
        if (not self.active or not self.identity or not self.game
                or self.game.board.fen() != self.identity[0]):
            return
        if kind == 'info':
            self._sync_gpu(active=True)
            self.lines[info['multipv']] = info
            if not self.render_timer.isActive():
                self.render_timer.start()
        elif kind == 'error':
            self._status('Leela: ' + info.get('message', 'Engine error'))
        elif kind == 'result':
            self._sync_gpu()
            self.completed_cache.add(self.identity)
            self.render_timer.stop()
            self._render()
            nodes = max((line.get('nodes', 0) for line in self.lines.values()), default=0)
            self._status('Leela · analysis complete' if nodes >= 10000 else
                         'Leela · short search: increase the search limit for more reliable contempt results')

    def _wdl(self, info):
        values = info.get('wdl')
        if values and self.game.board.turn != (1 if self.config['leela_side'] == 'white' else -1):
            values = values[::-1]
        return values

    def _render(self):
        if (not self.active or not self.identity or not self.game
                or self.game.board.fen() != self.identity[0]):
            return
        light = bool(QApplication.instance().property('nocturneLightAppearance'))
        colors = palette(light)
        for rank in sorted(self.lines):
            info = self.lines[rank]
            if rank not in self.rows:
                frame = QWidget()
                row = QHBoxLayout(frame)
                row.setContentsMargins(0, 2, 0, 2)
                moves = MoveText(auto_fit=True, reserved_lines=1)
                moves.candidate_rank = rank
                moves.font_increase = self.config.get('pv_font_increase', 20)
                badge = QLabel()
                badge.setFixedWidth(140)
                row.addWidget(moves, 1)
                row.addWidget(badge)
                moves.move_hovered.connect(lambda ply, r=rank: self._hover(r, ply))
                moves.move_clicked.connect(lambda ply, r=rank: self.line_selected.emit(self.lines[r]['pv'][:ply]))
                moves.pointer_moved.connect(self.pointer_moved)
                moves.preview_ended.connect(self.leave_timer.start)
                moves.preview_gap_ended.connect(self.leave_timer.start)
                self.variations.addWidget(frame)
                self.rows[rank] = (moves, badge, frame)
            moves, badge, frame = self.rows[rank]
            frame.show()
            frame_style = 'background: ' + colors['soft'] + ';' if rank % 2 == 0 else ''
            if frame.styleSheet() != frame_style:
                frame.setStyleSheet(frame_style)
            moves.set_font_increase(self.config.get('pv_font_increase', 20))
            moves.candidate_turn = self.game.board.turn
            moves.candidate_evaluation = score_label(info, self.game.board.turn)
            moves.candidate_depth = info.get('depth') or None
            moves.set_moves([(text, i + 1) for i, text in enumerate(info['san'])], light=light, figurines=True)
            wdl = self._wdl(info)
            badge.setText(' / '.join(f'{n/10:.1f}' for n in wdl) if wdl else '— / — / —')
            badge.setToolTip('Win / draw / loss percentages for ' + self.config['leela_side'] +
                             '. Evaluation uses Lc0’s centipawn conversion, in White’s perspective.')
            badge_style = f"color: {colors['maia']}; background: {colors['maia_soft']}; padding: 3px;"
            if badge.styleSheet() != badge_style:
                badge.setStyleSheet(badge_style)
            if rank == 1 and wdl:
                self.outcome.setText(f'{self.config["leela_side"].title()}: Win {wdl[0]/10:.1f}%   Draw {wdl[1]/10:.1f}%   Loss {wdl[2]/10:.1f}%')
        if self.lines:
            depth = max(info.get('depth', 0) for info in self.lines.values())
            seldepth = max(info.get('seldepth', 0) for info in self.lines.values())
            nodes = max(info.get('nodes', 0) for info in self.lines.values())
            nps = max(info.get('nps', 0) for info in self.lines.values())
            self.telemetry.setText(f'Depth {depth} · Selective depth {seldepth} · Nodes {nodes:,} · Nodes/second {nps:,}')
            self.telemetry.setToolTip('Lc0 reports search depth and selective depth. These describe its tree search and are not directly comparable to Stockfish depth.')
        self.cache[self.identity] = dict(self.lines)
        self.cache.move_to_end(self.identity)
        while len(self.cache) > 128:
            old_key, _ = self.cache.popitem(last=False)
            self.completed_cache.discard(old_key)
        self.results_changed.emit(self.lines)

    def _hover(self, rank, ply):
        self.leave_timer.stop()
        if rank in self.lines:
            self.preview.emit(self.lines[rank]['pv'], ply)

    def stop(self):
        self.active = False
        self.identity = None
        self.timer.stop()
        self.leave_timer.stop()
        self.preview_end.emit()
        self.render_timer.stop()
        self.engine.stop()

    def shutdown(self):
        self.stop()
        self.engine.connection.close()
        if self.installer and self.installer.isRunning():
            self.installer.requestInterruption()
            self.installer.wait(65000)
