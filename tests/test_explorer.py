"""Offline HTTP/Qt integration and rules checks for the public opening explorer."""

import json
import os
import socket
from pathlib import Path
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QDate, QTimer, Qt, QUrl, QUrlQuery
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QNetworkProxy, QNetworkRequest, QTcpServer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from nocturne.core.game import Game
from nocturne.core.rules import Board
from nocturne.explorer import ExplorerCache, ExplorerQuery, RATINGS, chessdb_score, parse_statistics
from nocturne.gui.explorer_client import ExplorerClient
from nocturne.gui.explorer_dialogs import ExplorerFiltersDialog, ExplorerGamesDialog, lichess_game_url
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
        # The client URL below uses IPv4 explicitly; bind the fixture to the
        # same address because Windows may resolve LocalHost to IPv6 only.
        if not self.listen(QHostAddress("127.0.0.1"), 0):
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
        params = parse_qs(urlsplit(path).query)
        body = self.body(path) if callable(self.body) else self.body
        if body is None:
            fen = params.get("fen", params.get("board"))[0]
            body = json.dumps(statistics(fen)).encode()
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
    def test_early_timer_rearms_before_network_dispatch(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            client = ExplorerClient(ExplorerCache(Path(directory) / "cache.sqlite3"), interval_ms=90)
            client.query = ExplorerQuery(Game().board.fen())
            client.last_sent = 10.0
            client._send_after = 10.09
            try:
                with patch("nocturne.gui.explorer_client.time.monotonic", return_value=10.063), \
                        patch.object(client, "request_for") as request:
                    client._send()
                    request.assert_not_called()
                    self.assertTrue(client.timer.isActive())
                    self.assertGreater(client.timer.remainingTime(), 0)
                with patch("nocturne.gui.explorer_client.time.monotonic", return_value=10.091), \
                        patch.object(client, "request_for", side_effect=RuntimeError("dispatch reached")):
                    with self.assertRaisesRegex(RuntimeError, "dispatch reached"):
                        client._send()
                client.blocked_until = 12.0
                client.query = ExplorerQuery(Game().board.fen(), "chessdb")
                self.assertEqual(client.blocked_until, 0)
                client.blocked_until = 15.0
                client.query = ExplorerQuery(Game().board.fen(), "lichess")
                self.assertEqual(client.blocked_until, 12.0)
                client.query = ExplorerQuery(Game().board.fen())
                with patch("nocturne.gui.explorer_client.time.monotonic", return_value=11.0), \
                        patch.object(client, "request_for") as request:
                    client._send()
                    request.assert_not_called()
            finally:
                client.close()
                client.deleteLater()
                app.processEvents()

    def test_chessdb_query_is_read_only_and_scores_remain_distinct_from_game_counts(self):
        query = ExplorerQuery(Game().board.fen(), "chessdb")
        params = parse_qs(urlsplit(query.url()).query)
        self.assertEqual(urlsplit(query.url()).netloc, "www.chessdb.cn")
        self.assertEqual(params["action"], ["queryall"])
        self.assertEqual(params["learn"], ["0"])
        self.assertEqual(params["json"], ["1"])
        data = {"status": "ok", "moves": [
            {"uci": "d2d4", "score": "??"}, {"uci": "e2e4", "score": 28, "note": "service note"}]}
        result = parse_statistics(data, query)
        self.assertEqual(result["moves"][0]["uci"], "e2e4")
        self.assertNotIn("total", result)
        self.assertNotIn("white", result["moves"][0])
        self.assertEqual(chessdb_score(28, query.fen), "+0.28")
        board = Game().board
        board.play_uci("e2e4")
        self.assertEqual(chessdb_score(28, board.fen()), "-0.28")
        self.assertEqual(chessdb_score(29999, board.fen()), "DB -29999")
        self.assertEqual(chessdb_score("??", query.fen), "Unscored")
        changed_clock = query.fen.rsplit(" ", 2)[0] + " 80 1"
        self.assertNotEqual(query.key, ExplorerQuery(changed_clock, "chessdb").key)

    def test_chessdb_unknown_terminal_and_illegal_data_handling(self):
        query = ExplorerQuery(Game().board.fen(), "chessdb")
        self.assertEqual(parse_statistics({"status": "unknown"}, query)["moves"], [])
        for payload in ({"status": "error"}, {"status": "checkmate"},
                        {"status": "ok", "moves": [{"uci": "e2e5", "score": 10}]},
                        {"status": "ok", "moves": [{"uci": "e2e4", "score": True}]}):
            with self.assertRaises(ValueError):
                parse_statistics(payload, query)
        mate = ExplorerQuery("7k/6Q1/5K2/8/8/8/8/8 b - - 0 1", "chessdb")
        self.assertEqual(parse_statistics({"status": "checkmate"}, mate)["status"], "checkmate")
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

    def test_advanced_filters_and_game_samples_have_separate_cache_keys(self):
        fen = Game().board.fen()
        players = ExplorerQuery(fen, "lichess", "rapid", since="2024-02", until="2025-06",
                                groups=(2200, 1600, 2200), include_games=True)
        params = parse_qs(urlsplit(players.url()).query)
        self.assertEqual(params["ratings"], ["1600,2200"])
        self.assertEqual(params["since"], ["2024-02"])
        self.assertEqual(params["until"], ["2025-06"])
        self.assertEqual(params["recentGames"], ["4"])
        masters = ExplorerQuery(fen, since="2024-02", groups=(1600,), include_games=True)
        params = parse_qs(urlsplit(masters.url()).query)
        self.assertNotIn("ratings", params)
        self.assertEqual(params["topGames"], ["15"])
        self.assertNotEqual(masters.key, ExplorerQuery(fen, since="2024-02").key)
        self.assertNotEqual(ExplorerQuery(fen, since="2024-02").key, ExplorerQuery(fen).key)
        self.assertEqual(ExplorerQuery(fen, "chessdb", since="2024-02").key, ExplorerQuery(fen, "chessdb").key)
        with self.assertRaises(ValueError):
            ExplorerQuery(fen, since="2025-02", until="2024-02")

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
        self.client = ExplorerClient(self.cache, base_url=self.server.base_url, debounce_ms=0, interval_ms=0, timeout_ms=5000)
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

    def wait_for(self, condition, seconds=7):
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

    def test_game_samples_and_pgn_use_current_position_and_only_official_token_scope(self):
        board = Board()
        board.play_uci("e2e4")
        query = ExplorerQuery(board.fen(), "masters", since="2021-01")
        game = {"id": "abcdefgh", "uci": "c7c5", "san": "untrusted SAN", "winner": None,
                "white": {"name": "Example White", "rating": 2500}, "black": {"name": "Example Black", "rating": 2510},
                "month": "2024-10", "year": 2024}
        pgn = b'[Event "Example"]\n[Result "1/2-1/2"]\n\n1. e4 c5 2. Nf3 d6 1/2-1/2\n'
        payload = statistics(query.fen) | {"topGames": [game, game | {"id": "../bad"}, game | {"uci": "c5c7"}]}
        self.server.body = lambda path: pgn if path.endswith("/pgn/abcdefgh") else json.dumps(payload).encode()
        self.client.set_lichess_token("test-token")
        masters = self.client.game_request("masters", "abcdefgh")
        players = self.client.game_request("lichess", "abcdefgh")
        self.assertEqual(masters.url().host(), "explorer.lichess.org")
        self.assertEqual(bytes(masters.rawHeader("Authorization")), b"Bearer test-token")
        self.assertEqual(players.url().host(), "lichess.org")
        self.assertFalse(players.hasRawHeader("Authorization"))
        master_link = lichess_game_url(query, "pFFH80NC", flipped=True)
        self.assertEqual(master_link.host(), "lichess.org")
        self.assertEqual(master_link.path(), "/import/master/pFFH80NC/black")
        self.assertEqual(QUrlQuery(master_link).queryItemValue("fen", QUrl.ComponentFormattingOption.FullyDecoded), query.fen)
        online_link = lichess_game_url(ExplorerQuery(query.fen, "lichess"), "abcdefgh")
        self.assertEqual(online_link.path(), "/game/abcdefgh/white")
        dialog = ExplorerGamesDialog(self.client, query)
        self.addCleanup(dialog.deleteLater)
        dialog.load()
        self.wait_for(lambda: dialog.table.rowCount() == 1)
        self.assertIn("Example White (2500)", dialog.table.item(0, 1).text())
        self.assertEqual(dialog.table.item(0, 3).text(), "c5")
        self.assertEqual(dialog.table.item(0, 5).text(), "2024-10")
        with patch("nocturne.gui.explorer_dialogs.QDesktopServices.openUrl", return_value=True) as browser:
            dialog.open_lichess.click()
            self.assertEqual(browser.call_args.args[0].path(), "/import/master/abcdefgh/white")
        self.assertIn("since=2021-01", self.server.requests[0][1])
        self.assertIn("topGames=15", self.server.requests[0][1])
        mock_request = QNetworkRequest(QUrl(self.server.base_url + "/masters/pgn/abcdefgh"))
        with patch.object(self.client, "game_request", return_value=mock_request):
            dialog.open_game.click()
            self.wait_for(lambda: dialog.game is not None)
        self.assertEqual(dialog.game.cursor, 1)
        self.assertEqual(dialog.game.sans, ["e4", "c5", "Nf3", "d6"])

    def test_games_dialog_combines_played_move_and_sample_list_filters(self):
        query = ExplorerQuery(self.query.fen, "lichess", include_games=True)
        first = {"id": "abcdefgh", "uci": "e2e4", "winner": "white",
                 "white": {"name": "White", "rating": 2500}, "black": {"name": "Black", "rating": 2400}}
        second = first | {"id": "abcd1234", "uci": "d2d4"}
        data = parse_statistics(statistics(query.fen) | {"topGames": [first], "recentGames": [first, second]}, query)
        dialog = ExplorerGamesDialog(self.client, query)
        self.addCleanup(dialog.deleteLater)
        dialog._result(query.key, data, "Cached · Lichess players")
        self.assertEqual(dialog.table.rowCount(), 2)
        self.assertEqual(dialog.table.item(0, 0).text(), "Top, Recent")
        dialog.list_filter.setCurrentIndex(dialog.list_filter.findData("Recent"))
        dialog.move_filter.setCurrentIndex(dialog.move_filter.findData("d2d4"))
        self.assertEqual(dialog.table.rowCount(), 1)
        self.assertEqual(dialog.table.item(0, 3).text(), "d4")
        dialog.list_filter.setCurrentIndex(dialog.list_filter.findData("Top"))
        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertFalse(dialog.open_lichess.isEnabled())

    def test_chessdb_json_adapter_and_semantic_rate_limit(self):
        query = ExplorerQuery(self.query.fen, "chessdb")
        self.server.body = json.dumps({"status": "ok", "moves": [{"uci": "e2e4", "score": 28}]}).encode()
        self.client.load(query)
        self.wait_for(lambda: bool(self.results))
        self.assertEqual(self.results[-1][1]["moves"][0]["score"], 28)
        self.assertIn("/cdb.php?", self.server.requests[0][1])
        self.server.body = b'{"status":"rate limit exceeded"}'
        self.client.load(query, force=True)
        self.wait_for(lambda: "ChessDB rate limit" in self.status[-1])
        self.assertIn("showing saved statistics", self.status[-1])
        self.assertGreater(self.client.blocked_until - time.monotonic(), 59)

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
        for code, body, expected in ((503, b"unavailable", "HTTP 503"), (401, b"unauthorized", "access token required"), (200, b"{broken", "invalid"),
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

    def test_tablebase_panel_uses_public_endpoint_and_restores_opening_fallback(self):
        import chess
        from nocturne.gui.explorer_panel import OpeningExplorer

        panel_directory = tempfile.TemporaryDirectory()
        self.addCleanup(panel_directory.cleanup)
        explorer = OpeningExplorer(Path(panel_directory.name) / "panel.db")
        client = explorer.client
        self.addCleanup(explorer.deleteLater)
        self.addCleanup(explorer.close_client)
        client.set_lichess_token("test_token")
        client.base_url = self.server.base_url
        client.debounce_ms = client.interval_ms = 0
        client.network.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        fen = "4k3/6KP/8/8/8/8/7p/8 w - - 13 33"
        board = Board(fen)
        query = ExplorerQuery(fen, "tablebase")
        with patch.object(client, "base_url", None):
            official = client.request_for(query)
            self.assertEqual(official.url().host(), "tablebase.lichess.ovh")
            self.assertFalse(official.rawHeader("Authorization"))
        self.assertTrue(query.fen.endswith("13 1"))
        self.assertNotEqual(query.key, ExplorerQuery(fen.replace("13 33", "0 33"), "tablebase").key)

        legal = list(chess.Board(fen).legal_moves)
        legal.sort(key=lambda move: move.uci() != "h7h8q")
        self.server.body = json.dumps({
            "category": "win",
            "moves": [{"uci": move.uci(), "san": "ignored", "category": "loss" if i == 0 else "draw",
                       "dtz": -2 if i == 0 else 0} for i, move in enumerate(legal)],
        }).encode()
        explorer.set_position(board, "endgame", True, "masters", endgame=True)
        self.wait_for(lambda: bool(explorer.rows))
        self.assertEqual(urlsplit(self.server.requests[0][1]).path, "/standard")
        self.assertEqual(explorer.title.text(), "Endgame Tablebase")
        self.assertEqual([explorer.table.item(0, i).text() for i in range(3)], ["h8=Q+", "Win", "2"])

        selected = []
        explorer.move_selected.connect(lambda *args: selected.append(args))
        explorer.table.setCurrentCell(0, 0)
        QTest.keyClick(explorer.table, Qt.Key.Key_Return)
        self.assertEqual(selected, [("endgame", "h7h8q")])

        def unknown_tablebase(path):
            if urlsplit(path).path == "/standard":
                return b'{"category":"unknown","moves":[]}'
            return None

        self.server.body = unknown_tablebase
        other = Board(fen.replace("13 33", "14 33"))
        explorer.set_position(other, "other", True, "masters", endgame=True)
        self.wait_for(lambda: explorer.query.source == "masters")
        self.wait_for(lambda: bool(explorer.rows))
        self.assertEqual([urlsplit(path).path for _, path in self.server.requests],
                         ["/standard", "/standard", "/masters"])
        explorer.set_position(other, "other", True, "masters", endgame=True)
        self.assertEqual(explorer.query.source, "masters")
        explorer.set_position(Board(), "opening", True, "masters", endgame=True)
        self.assertEqual(explorer.query.source, "masters")

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

    def test_filters_dialog_accepts_disjoint_bands_and_rejects_inverted_dates(self):
        dialog = ExplorerFiltersDialog("lichess", "2025-01", "2024-12", 0, (1600, 2200))
        self.addCleanup(dialog.deleteLater)
        dialog.accept()
        self.assertIn("first month", dialog.message.text())
        dialog.last_month.setText("2025-06")
        dialog.accept()
        self.assertEqual(dialog.values, ("2025-01", "2025-06", (1600, 2200)))

    def test_masters_calendar_and_player_rating_controls(self):
        dialog = ExplorerFiltersDialog("masters", "", "", 0, ())
        self.addCleanup(dialog.deleteLater)
        dialog.show()
        self.assertFalse(dialog.bands[1600].isEnabled())
        QTest.mouseClick(dialog.first_month, Qt.MouseButton.LeftButton)
        self.assertTrue(dialog.first_month.calendar.isVisible())
        dialog.first_month.calendar.clicked.emit(QDate(2025, 4, 24))
        self.assertEqual(dialog.first_month.text(), "2025-04")
        self.assertFalse(dialog.first_month.calendar.isVisible())
        dialog.source.setCurrentIndex(dialog.source.findData("lichess"))
        self.assertTrue(dialog.bands[1600].isEnabled())
        dialog.close()

    def test_explorer_header_links_to_game_or_current_position(self):
        from nocturne.gui.explorer_panel import OpeningExplorer

        with tempfile.TemporaryDirectory() as directory:
            explorer = OpeningExplorer(Path(directory) / "cache.sqlite3")
            try:
                explorer.query = ExplorerQuery(Game().board.fen())
                explorer._clear_statistics()
                with patch("nocturne.gui.explorer_panel.QDesktopServices.openUrl", return_value=True) as open_url:
                    explorer.lichess_button.click()
                    self.assertTrue(open_url.call_args.args[0].path().startswith("/analysis/standard/"))
                    explorer.lichess_game_id = "pFFH80NC"
                    explorer.lichess_button.click()
                    self.assertEqual(open_url.call_args.args[0].path(), "/import/master/pFFH80NC/white")
            finally:
                explorer.close_client()
                explorer.deleteLater()

    def test_empty_explorer_collapses_and_expands_again_when_moves_return(self):
        from nocturne.gui.explorer_panel import OpeningExplorer

        with tempfile.TemporaryDirectory() as directory:
            explorer = OpeningExplorer(Path(directory) / "cache.sqlite3")
            try:
                query = ExplorerQuery(Game().board.fen())
                explorer.query = query
                empty = statistics(query.fen) | {"total": 0, "moves": []}
                explorer._result(query.key, empty, "Cached · Lichess Masters")
                self.assertIn("No games found", explorer.summary.text())
                self.assertLessEqual(explorer.maximumHeight(), 88)
                self.assertTrue(explorer.table.isHidden())

                populated = statistics(query.fen) | {"total": 20}
                for row in populated["moves"]:
                    row["total"] = 20
                explorer._result(query.key, populated, "Cached · Lichess Masters")
                self.assertEqual(explorer.maximumHeight(), 16777215)
                self.assertFalse(explorer.table.isHidden())
                selected = []
                explorer.identity = "current-position"
                explorer.move_selected.connect(lambda identity, move: selected.append((identity, move)))
                explorer.table.setCurrentCell(1, 0)
                QTest.keyClick(explorer.table, Qt.Key.Key_Return)
                self.assertEqual(selected, [("current-position", populated["moves"][1]["uci"])])
            finally:
                explorer.close_client()

    def test_lichess_session_token_is_host_scoped_and_never_saved(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        window = MainWindow(Path(directory.name))
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window._analysis_enabled = False
        client = window.explorer.client
        self.assertEqual(window.config["explorer_source"], "chessdb")
        query = ExplorerQuery(window.game.board.fen())
        client.query = query
        client.status.emit(query.key, "Lichess Masters unavailable (HTTP 500)")
        self.assertTrue(window.lichess_token_action.text().startswith("⚠"))
        self.assertIn("background:#694b20", window.lichess_token_row.styleSheet())
        client.status.emit(query.key, "Lichess Masters access token required · Database → Lichess access token…")
        self.assertTrue(window.lichess_token_action.text().startswith("⚠"))
        self.assertTrue(window.lichess_token_action.font().bold())
        with patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("lip_unit_test_only", True)) as dialog:
            window._lichess_token_dialog()
        from PySide6.QtWidgets import QLineEdit
        self.assertEqual(dialog.call_args.args[-1], QLineEdit.EchoMode.Password)
        self.assertEqual(window.config["explorer_source"], "masters")
        self.assertTrue(window.opening_coverage.client.has_lichess_token)
        self.assertEqual(window.lichess_token_action.text(), "Lichess access token…")
        self.assertEqual(bytes(client.request_for(query).rawHeader("Authorization")), b"Bearer lip_unit_test_only")
        self.assertEqual(bytes(client.request_for(ExplorerQuery(query.fen, "chessdb")).rawHeader("Authorization")), b"")
        for other in ("https://example.test", "http://explorer.lichess.org", "https://explorer.lichess.org:444"):
            client.base_url = other
            self.assertEqual(bytes(client.request_for(query).rawHeader("Authorization")), b"")
        client.base_url = None
        with self.assertRaises(ValueError):
            client.set_lichess_token("bad\r\nheader")
        window._save()
        self.assertFalse(any("lip_unit_test_only" in line for line in window.store.db.iterdump()))
        self.assertTrue(window.clear_lichess_token_action.isEnabled())
        window._clear_lichess_token()
        self.assertEqual(window.config["explorer_source"], "chessdb")
        self.assertFalse(client.has_lichess_token)
        self.assertFalse(window.clear_lichess_token_action.isEnabled())

    def test_saved_lichess_source_falls_back_to_chessdb_without_a_session_token(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        window = MainWindow(Path(directory.name))
        self.addCleanup(window.deleteLater)
        window.config["explorer_source"] = "lichess"
        window._save()
        window.close()
        reopened = MainWindow(Path(directory.name))
        self.addCleanup(reopened.deleteLater)
        self.addCleanup(reopened.close)
        self.assertFalse(reopened.explorer.client.has_lichess_token)
        self.assertEqual(reopened.config["explorer_source"], "chessdb")
        self.assertTrue(reopened.explorer_actions[("explorer_source", "chessdb")].isChecked())

    def test_chessdb_menu_uses_score_columns_and_clicks_create_variations(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        window = MainWindow(Path(directory.name))
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window._analysis_enabled = False
        window.timer.stop()
        window.autosave_timer.stop()
        window.game = Game.from_pgn("1.d4 d5 *")
        window.game.navigate(0)
        query = ExplorerQuery(window.game.board.fen(), "chessdb")
        window.explorer.client.cache.put(query.key, {"status": "ok", "moves": [
            {"uci": "e2e4", "score": 28, "note": "Fixture"}, {"uci": "g1f3", "score": "??"}]})
        window._refresh()
        window.show()
        window.explorer_actions[("explorer_source", "chessdb")].trigger()
        window._set_explorer_option("explorer_enabled", True)
        self.app.processEvents()
        self.assertEqual(window.explorer.table.horizontalHeaderItem(1).text(), "Score · White")
        self.assertEqual(window.explorer.table.item(0, 1).text(), "+0.28")
        self.assertFalse(window.explorer_filter_menus[0].isEnabled())
        self.assertEqual(window.explorer.table.item(1, 1).text(), "Unscored")
        window.explorer._click(0, 0)
        self.assertEqual(window.game.sans, ["e4"])
        self.assertIn("d4", window.game.pgn())
        self.assertIn("(", window.game.pgn())
        window._set_explorer_option("explorer_enabled", False)

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

    def test_hidden_explorer_keeps_lookup_for_new_positions_and_source_changes(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        window = MainWindow(Path(directory.name))
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window._analysis_enabled = False
        window.timer.stop()
        window.autosave_timer.stop()
        window.game = Game.from_pgn("1.e4 e5 *")
        for ply in (0, 1, 2):
            window.game.navigate(ply)
            query = ExplorerQuery(window.game.board.fen())
            window.explorer.client.cache.put(query.key, statistics(query.fen))
        window._choose_explorer("masters")
        window.show()
        self.app.processEvents()
        self.assertFalse(window.explorer.isVisible())
        self.assertTrue(window.explorer.statistics)
        old = window.explorer.query
        window._navigate(1)
        self.assertFalse(window.explorer.isVisible())
        self.assertNotEqual(window.explorer.query.key, old.key)
        self.assertTrue(window.explorer.statistics)
        self.assertEqual(window.explorer.identity, window._position_identity())
        self.assertFalse(window.explorer.client.timer.isActive())
        query = ExplorerQuery(window.game.board.fen(), "lichess")
        window.explorer.client.cache.put(query.key, statistics(query.fen))
        window._choose_explorer("lichess")
        self.assertFalse(window.explorer.isVisible())
        self.assertEqual(window.explorer.query.key, query.key)
        self.assertTrue(window.explorer.statistics)
        window._set_explorer_option("explorer_enabled", True)
        window.explorer._preview(0, 0)
        self.assertIsNone(window.board_view.preview_board)
        self.assertFalse(window.hover_preview.isHidden())
        window.explorer.close_requested.emit()
        self.assertFalse(window.explorer.isVisible())
        self.assertIsNone(window.board_view.preview_board)
        self.assertTrue(window.hover_preview.isHidden())
        self.assertTrue(window.explorer.statistics)
        self.assertTrue(window.store.get("settings")["explorer_statistics"])
        self.assertFalse(window.store.get("settings")["explorer_enabled"])
        window._set_explorer_option("explorer_statistics", False)
        self.assertIsNone(window.explorer.query)
        self.assertFalse(window.explorer.client.timer.isActive())

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
        window._set_explorer_option("explorer_enabled", True)
        self.app.processEvents()
        self.assertTrue(window.explorer.rows)
        identity = window._position_identity()
        row = window.explorer.rows[0]
        window.explorer._preview(0, 0)
        self.assertIsNone(window.board_view.preview_board)
        self.assertFalse(window.hover_preview.isHidden())
        self.assertEqual(window.game.board.fen(), before)
        window.explorer._end_preview()
        self.assertIsNone(window.board_view.preview_board)
        self.assertTrue(window.hover_preview.isHidden())
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
        self.assertIsNotNone(window.explorer.query)
        window._set_explorer_option("explorer_statistics", False)
        self.assertIsNone(window.explorer.query)
        self.assertIsNone(window.explorer.client.reply)
        self.assertFalse(window.explorer.client.timer.isActive())
