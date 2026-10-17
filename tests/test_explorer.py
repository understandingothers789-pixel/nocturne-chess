"""Offline HTTP/Qt integration and rules checks for the public opening explorer."""

import json
import os
import socket
from pathlib import Path
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlsplit

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer, Qt
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QNetworkProxy, QTcpServer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from nocturne.core.game import Game
from nocturne.core.rules import Board
from nocturne.explorer import ExplorerCache, ExplorerQuery, RATINGS, parse_statistics
from nocturne.gui.explorer_client import ExplorerClient
from nocturne.gui.window import MainWindow


def statistics(fen):
    board = Board(fen)
    moves = list(board.legal_moves())[:3]
    return {"white": 50, "draws": 20, "black": 30,
            "opening": {"eco": "A00", "name": "HTTP fixture · test data"},
            "moves": [{"uci": m.uci(), "san": "untrusted SAN", "white": 10, "draws": 5, "black": 5}
                      for m in moves]}


class HttpFixture(QTcpServer):
    def __init__(self):
        super().__init__()
        try:
            probe = socket.socket()
            probe.close()
        except PermissionError:
            raise unittest.SkipTest("Execution sandbox denies loopback sockets")
        self.requests = []
        self.peers = []
        self.timers = []
        self.code, self.delay, self.body = 200, 0, None
        self.newConnection.connect(self._accept)
        if not self.listen(QHostAddress.SpecialAddress.LocalHost, 0):
            if self.serverError() == QAbstractSocket.SocketError.SocketAccessError:
                raise unittest.SkipTest("Execution sandbox denies loopback sockets")
            raise RuntimeError(self.errorString())

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.serverPort()}"

    def _accept(self):
        while self.hasPendingConnections():
            peer = self.nextPendingConnection()
            self.peers.append(peer)
            peer._request = bytearray()
            peer._handled = False
            peer.readyRead.connect(lambda p=peer: self._read(p))

    def _read(self, peer):
        peer._request.extend(bytes(peer.readAll()))
        if peer._handled or b"\r\n\r\n" not in peer._request:
            return
        peer._handled = True
        path = peer._request.split(b" ")[1].decode()
        self.requests.append((time.monotonic(), path))
        fen = parse_qs(urlsplit(path).query)["fen"][0]
        body = self.body if self.body is not None else json.dumps(statistics(fen)).encode()
        response = (f"HTTP/1.1 {self.code} Response\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\nRetry-After: 2\r\nConnection: close\r\n\r\n").encode() + body

        def send():
            if peer.state() == peer.SocketState.ConnectedState:
                peer.write(response)
                peer.disconnectFromHost()

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(send)
        self.timers.append(timer)
        timer.start(self.delay)

    def shutdown(self):
        for timer in self.timers:
            timer.stop()
        for peer in self.peers:
            peer.abort()
        self.close()
        self.deleteLater()


class DataTests(unittest.TestCase):
    def test_url_filters_counters_and_source_isolation(self):
        root = Game().board.fen()
        q = ExplorerQuery(root, "lichess", "rapid", 1800)
        params = parse_qs(urlsplit(q.url()).query)
        self.assertEqual(urlsplit(q.url()).netloc, "explorer.lichess.org")
        self.assertEqual(params["ratings"], ["1800,2000,2200,2500"])
        self.assertEqual(params["speeds"], ["rapid"])
        self.assertNotIn("ratings", parse_qs(urlsplit(ExplorerQuery(root).url()).query))
        self.assertNotEqual(q.key, ExplorerQuery(root).key)
        self.assertEqual(ExplorerQuery(root).key, ExplorerQuery(root.rsplit(" ", 2)[0] + " 42 71").key)
        self.assertEqual(parse_qs(urlsplit(ExplorerQuery(root, "lichess").url()).query)["ratings"], [",".join(map(str, RATINGS))])
        for kwargs in ({"source": "other"}, {"speed": "other"}, {"rating": 400}):
            with self.assertRaises(ValueError):
                ExplorerQuery(root, **kwargs)

    def test_response_recomputes_san_and_rejects_illegal_or_invalid_counts(self):
        query = ExplorerQuery(Game().board.fen())
        result = parse_statistics(statistics(query.fen), query)
        self.assertEqual(result["total"], 100)
        self.assertNotEqual(result["moves"][0]["san"], "untrusted SAN")
        for wrong in ("e2e5", "0000"):
            data = statistics(query.fen)
            data["moves"][0]["uci"] = wrong
            with self.assertRaises(ValueError):
                parse_statistics(data, query)
        for wrong in (-1, True, "10", 10**20):
            data = statistics(query.fen)
            data["white"] = wrong
            with self.assertRaises(ValueError):
                parse_statistics(data, query)

    def test_cache_persists_bounds_and_recovers_from_corrupt_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.db"
            cache = ExplorerCache(path, limit=2)
            for i in range(3):
                cache.put(str(i), {"test": i}, stamp=i)
            cache.close()
            cache = ExplorerCache(path)
            self.assertIsNone(cache.get("0"))
            self.assertEqual(cache.get("2"), (2.0, {"test": 2}))
            cache.db.execute("UPDATE positions SET payload='broken' WHERE key='2'")
            cache.db.commit()
            self.assertIsNone(cache.get("2"))
            cache.close()
            path.write_bytes(b"not a SQLite database")
            cache = ExplorerCache(path)
            self.assertIsNone(cache.get("x"))
            cache.put("x", {})
            cache.close()


class NetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.server = HttpFixture()
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = ExplorerCache(Path(self.tmp.name) / "cache.db")
        self.client = ExplorerClient(self.cache, base_url=self.server.base_url, debounce_ms=0, interval_ms=0, timeout_ms=500)
        self.client.network.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.results, self.status = [], []
        self.client.result.connect(lambda *args: self.results.append(args))
        self.client.status.connect(lambda key, message: self.status.append(message))
        self.query = ExplorerQuery(Game().board.fen())

    def tearDown(self):
        self.client.close()
        self.client.deleteLater()
        self.server.shutdown()
        self.app.processEvents()
        self.tmp.cleanup()

    def wait_for(self, condition, seconds=2):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not condition():
            self.app.processEvents()
            QTest.qWait(5)
        self.assertTrue(condition(), self.status)

    def test_live_response_then_cached_response_without_a_second_request(self):
        self.client.load(self.query)
        self.wait_for(lambda: bool(self.results))
        self.assertTrue(self.results[-1][2].startswith("Live"))
        self.client.load(self.query)
        self.assertTrue(self.results[-1][2].startswith("Cached"))
        QTest.qWait(30)
        self.assertEqual(len(self.server.requests), 1)

    def test_debounce_cancellation_and_late_results_do_not_change_current_position(self):
        self.client.debounce_ms = 30
        self.client.load(self.query)
        board = Game().board
        board.play_uci("e2e4")
        second = ExplorerQuery(board.fen())
        self.client.load(second)
        self.wait_for(lambda: bool(self.results))
        self.assertEqual(len(self.server.requests), 1)
        self.assertEqual(self.results[-1][0], second.key)
        self.server.delay = 120
        self.client.load(self.query, force=True)
        self.wait_for(lambda: len(self.server.requests) == 2)
        self.client.load(second)
        QTest.qWait(150)
        self.assertEqual(self.results[-1][0], second.key)
        self.assertFalse(any(key == self.query.key for key, _, _ in self.results))

    def test_rate_limit_uses_saved_data_and_does_not_retry_in_a_loop(self):
        self.cache.put(self.query.key, statistics(self.query.fen), stamp=time.time() - 100000)
        self.server.code = 429
        self.client.load(self.query)
        self.wait_for(lambda: any("rate limit" in s for s in self.status))
        self.assertTrue(self.results)
        self.assertIn("showing saved statistics", self.status[-1])
        self.assertGreater(self.client.blocked_until - time.monotonic(), 59)
        self.client.load(self.query, force=True)
        QTest.qWait(30)
        self.assertEqual(len(self.server.requests), 1)

    def test_errors_invalid_payload_size_limit_timeout_and_close(self):
        for code, body, expected in ((503, b"unavailable", "HTTP 503"), (200, b"{broken", "invalid"),
                                      (200, b" " * (512 * 1024 + 1), "size limit")):
            self.server.code, self.server.body = code, body
            self.client.load(self.query, force=True)
            self.wait_for(lambda: self.client.reply is None and not self.client.timer.isActive())
            self.assertIn(expected, self.status[-1])
            self.assertFalse(self.results)
        self.server.body, self.server.delay = None, 200
        self.client.timeout_ms = 30
        self.client.load(self.query, force=True)
        self.wait_for(lambda: any("timed out" in s for s in self.status))
        self.client.load(self.query, force=True)
        self.client.cancel()
        QTest.qWait(50)
        self.assertIsNone(self.client.reply)
        self.assertFalse(self.results)

    def test_request_spacing(self):
        self.client.interval_ms = 90
        self.client.load(self.query)
        self.wait_for(lambda: bool(self.results))
        self.client.load(self.query, force=True)
        self.wait_for(lambda: len(self.server.requests) == 2)
        self.assertGreaterEqual(self.server.requests[1][0] - self.server.requests[0][0], 0.075)

class CachedGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_source_filters_pause_in_pgn_and_reopen_from_cache(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        window = MainWindow(Path(directory.name))
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window._analysis_enabled = False
        window.timer.stop()
        window.autosave_timer.stop()
        fen = window.game.board.fen()
        for query in (ExplorerQuery(fen, "lichess"), ExplorerQuery(fen, "lichess", "rapid"),
                      ExplorerQuery(fen, "lichess", "rapid", 1800)):
            window.explorer.client.cache.put(query.key, statistics(query.fen))
        window.show()
        window.explorer_actions[("explorer_source", "lichess")].trigger()
        window.explorer_actions[("explorer_speed", "rapid")].trigger()
        window.explorer_actions[("explorer_rating", 1800)].trigger()
        self.app.processEvents()
        self.assertTrue(window.explorer.rows)
        self.assertIn("rapid", window.explorer.title.text())
        self.assertIn("1800+", window.explorer.title.text())
        self.assertIsNone(window.explorer.client.reply)
        self.assertFalse(window.explorer.client.timer.isActive())
        window.tabs.setCurrentIndex(2)
        self.assertIsNone(window.explorer.query)
        window.tabs.setCurrentIndex(1)
        self.assertTrue(window.explorer.rows)
        window.game = Game("4k3/8/8/8/8/8/8/R4K1R w HA - 0 1")
        window._refresh()
        self.assertFalse(window.explorer.rows)
        self.assertIsNone(window.explorer.query)
        self.assertIn("Chess960", window.explorer.summary.text())

    def test_window_explorer_is_opt_in_and_click_preserves_original_branch(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        window = MainWindow(Path(directory.name) / "gui")
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.timer.stop()
        window.autosave_timer.stop()
        window._analysis_enabled = False
        query = ExplorerQuery(window.game.board.fen())
        window.explorer.client.cache.put(query.key, statistics(query.fen))
        window.show()
        self.app.processEvents()
        self.assertFalse(window.explorer.isVisible())
        self.assertFalse(window.explorer.client.timer.isActive())
        window.game = Game.from_pgn("1.e4 e5 *")
        window.game.navigate(0)
        before = window.game.board.fen()
        window._refresh()
        window.explorer_actions[("explorer_source", "masters")].trigger()
        self.app.processEvents()
        self.assertTrue(window.explorer.rows)
        identity = window._position_identity()
        row = window.explorer.rows[0]
        window.explorer._preview(0, 0)
        self.assertIsNotNone(window.board_view.preview_board)
        self.assertEqual(window.game.board.fen(), before)
        window.explorer._end_preview()
        self.assertIsNone(window.board_view.preview_board)
        rect = window.explorer.table.visualItemRect(window.explorer.table.item(0, 0))
        QTest.mouseClick(window.explorer.table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        self.assertEqual(window.game.moves[-1].uci(), row["uci"])
        self.assertIn("e4", window.game.pgn())
        self.assertIn("(", window.game.pgn())
        current = window.game.board.fen()
        window._explorer_move(identity, "d2d4")
        self.assertEqual(window.game.board.fen(), current)
        window._set_explorer_option("explorer_enabled", False)
        self.assertFalse(window.explorer.isVisible())
        self.assertIsNone(window.explorer.client.reply)
        self.assertFalse(window.explorer.client.timer.isActive())
