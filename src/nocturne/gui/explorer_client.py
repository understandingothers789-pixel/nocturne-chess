"""Non-blocking opening-explorer HTTP with cancellation, pacing and stale guards."""

import json
import math
import re
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Qt
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxyFactory, QNetworkReply, QNetworkRequest

from .. import __version__
from ..explorer import CACHE_AGE, MAX_RESPONSE, parse_statistics


class ExplorerClient(QObject):
    result = Signal(str, dict, str)
    status = Signal(str, str)

    def __init__(self, cache, parent=None, *, base_url=None, debounce_ms=350, interval_ms=1000, timeout_ms=10000):
        super().__init__(parent)
        self.cache = cache
        self.base_url = base_url
        self.debounce_ms, self.interval_ms, self.timeout_ms = debounce_ms, interval_ms, timeout_ms
        QNetworkProxyFactory.setUseSystemConfiguration(True)
        self.network = QNetworkAccessManager(self)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._send)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self._timeout)
        self.reply = None
        self.query = None
        self.generation = 0
        self.last_sent = -math.inf
        self._send_after = -math.inf
        self.blocked_until = 0
        self.saved = None
        self._lichess_token = ""

    @property
    def has_lichess_token(self):
        return bool(self._lichess_token)

    def set_lichess_token(self, token):
        token = token.strip()
        if token and not re.fullmatch(r"[A-Za-z0-9._~+/=-]{1,512}", token):
            raise ValueError("Enter a single-line Lichess access token")
        self._lichess_token = token

    def request_for(self, query):
        request = QNetworkRequest(QUrl(query.url(self.base_url)))
        request.setRawHeader(b"Accept", b"application/json")
        request.setRawHeader(b"User-Agent", f"NocturneChess/{__version__} (database explorer)".encode())
        official_lichess = (query.source in ("masters", "lichess") and request.url().scheme() == "https"
                            and request.url().host() == "explorer.lichess.org" and request.url().port(443) == 443)
        if official_lichess and self._lichess_token:
            request.setRawHeader(b"Authorization", b"Bearer " + self._lichess_token.encode())
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.SameOriginRedirectPolicy if official_lichess else
                             QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        request.setTransferTimeout(self.timeout_ms)
        return request

    def cancel(self):
        self.generation += 1
        self.timer.stop()
        self.deadline.stop()
        reply, self.reply = self.reply, None
        if reply:
            reply.abort()
            reply.deleteLater()

    def load(self, query, force=False):
        self.cancel()
        self.query = query
        self.saved = None
        cached = self.cache.get(query.key)
        if cached:
            try:
                stamp, data = cached
                self.saved = parse_statistics(data, query)
                origin = "Cached · " + time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp))
                self.result.emit(query.key, self.saved, origin)
                if not force and time.time() - stamp < CACHE_AGE:
                    self.status.emit(query.key, origin)
                    return
            except ValueError:
                self.saved = None
        if time.monotonic() < self.blocked_until:
            self._failed(f"{query.label} rate limit · retry in {math.ceil(self.blocked_until - time.monotonic())} s")
            return
        self.status.emit(query.key, f"Loading {query.label}…")
        wait = max(self.debounce_ms, self.interval_ms - (time.monotonic() - self.last_sent) * 1000)
        self._send_after = time.monotonic() + max(0, wait) / 1000
        self.timer.start(max(0, math.ceil(wait)))

    def _send(self):
        if self.query is None:
            return
        # Qt/platform timers can fire early. Enforce pacing using the clock at
        # dispatch, including debounce and Retry-After, rather than timer accuracy.
        now = time.monotonic()
        due = max(self._send_after, self.last_sent + self.interval_ms / 1000, self.blocked_until)
        if now < due:
            self.timer.start(max(1, math.ceil((due - now) * 1000)))
            return
        query, generation = self.query, self.generation
        request = self.request_for(query)
        self.last_sent = time.monotonic()
        reply = self.network.get(request)
        self.reply = reply
        reply._body = bytearray()
        reply._failure = ""
        reply.readyRead.connect(lambda: self._read(reply))
        reply.finished.connect(lambda: self._finished(reply, query, generation))
        self.deadline.start(self.timeout_ms)

    def _read(self, reply):
        reply._body.extend(bytes(reply.readAll()))
        if len(reply._body) > MAX_RESPONSE:
            reply._failure = f"{self.query.label} response exceeds the size limit"
            reply.abort()

    def _timeout(self):
        if self.reply:
            self.reply._failure = f"{self.query.label} request timed out"
            self.reply.abort()

    def _finished(self, reply, query, generation):
        if generation != self.generation or reply is not self.reply:
            reply.deleteLater()
            return
        self.deadline.stop()
        self.reply = None
        code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if code == 429:
            try:
                seconds = int(bytes(reply.rawHeader("Retry-After")))
            except ValueError:
                seconds = 60
            seconds = max(60, min(3600, seconds))
            self.blocked_until = time.monotonic() + seconds
            self._failed(f"{query.label} rate limit · retry in {seconds} s")
        elif code in (401, 403) and query.source in ("masters", "lichess"):
            self._failed(f"{query.label} access token required · Database → Lichess access token…")
        elif reply._failure:
            self._failed(reply._failure)
        elif reply.error() != QNetworkReply.NetworkError.NoError or code != 200:
            self._failed(f"{query.label} unavailable (HTTP {code})" if code else f"{query.label} unavailable · check your connection")
        else:
            self._read(reply)
            try:
                if reply._failure:
                    raise ValueError(reply._failure)
                payload = json.loads(reply._body)
                if query.source == "chessdb" and isinstance(payload, dict) and payload.get("status") == "rate limit exceeded":
                    self.blocked_until = time.monotonic() + 60
                    self._failed("ChessDB rate limit · retry in 60 s")
                    reply.deleteLater()
                    return
                data = parse_statistics(payload, query)
                self.cache.put(query.key, data)
                self.result.emit(query.key, data, f"Live · {query.label}")
                self.status.emit(query.key, f"Live · {query.label}")
            except (ValueError, TypeError, UnicodeError):
                self._failed(f"{query.label} returned invalid data")
        reply.deleteLater()

    def _failed(self, message):
        if self.saved:
            message += " · showing saved statistics"
        self.status.emit(self.query.key, message)

    def close(self):
        self.cancel()
        self._lichess_token = ""
        self.cache.close()
