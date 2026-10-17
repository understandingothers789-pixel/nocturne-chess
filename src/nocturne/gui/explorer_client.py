"""Non-blocking opening-explorer HTTP with cancellation, pacing and stale guards."""

import json
import math
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxyFactory, QNetworkReply, QNetworkRequest

from .. import __version__
from ..explorer import CACHE_AGE, EXPLORER_URL, MAX_RESPONSE, parse_statistics


class ExplorerClient(QObject):
    result = Signal(str, dict, str)
    status = Signal(str, str)

    def __init__(self, cache, parent=None, *, base_url=EXPLORER_URL, debounce_ms=350, interval_ms=1000, timeout_ms=10000):
        super().__init__(parent)
        self.cache = cache
        self.base_url = base_url
        self.debounce_ms, self.interval_ms, self.timeout_ms = debounce_ms, interval_ms, timeout_ms
        QNetworkProxyFactory.setUseSystemConfiguration(True)
        self.network = QNetworkAccessManager(self)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._send)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self._timeout)
        self.reply = None
        self.query = None
        self.generation = 0
        self.last_sent = -math.inf
        self.blocked_until = 0
        self.saved = None

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
            self._failed(f"Lichess rate limit · retry in {math.ceil(self.blocked_until - time.monotonic())} s")
            return
        self.status.emit(query.key, "Loading Lichess statistics…")
        wait = max(self.debounce_ms, self.interval_ms - (time.monotonic() - self.last_sent) * 1000)
        self.timer.start(max(0, math.ceil(wait)))

    def _send(self):
        query, generation = self.query, self.generation
        request = QNetworkRequest(QUrl(query.url(self.base_url)))
        request.setRawHeader(b"Accept", b"application/json")
        request.setRawHeader(b"User-Agent", f"NocturneChess/{__version__} (opening explorer)".encode())
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        request.setTransferTimeout(self.timeout_ms)
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
            reply._failure = "Lichess response exceeds the size limit"
            reply.abort()

    def _timeout(self):
        if self.reply:
            self.reply._failure = "Lichess request timed out"
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
            self._failed(f"Lichess rate limit · retry in {seconds} s")
        elif reply._failure:
            self._failed(reply._failure)
        elif reply.error() != QNetworkReply.NetworkError.NoError or code != 200:
            self._failed(f"Lichess unavailable (HTTP {code})" if code else "Lichess unavailable · check your connection")
        else:
            self._read(reply)
            try:
                if reply._failure:
                    raise ValueError(reply._failure)
                data = parse_statistics(json.loads(reply._body), query)
                self.cache.put(query.key, data)
                self.result.emit(query.key, data, "Live · Lichess opening explorer")
                self.status.emit(query.key, "Live · Lichess opening explorer")
            except (ValueError, TypeError, UnicodeError):
                self._failed("Lichess returned invalid opening statistics")
        reply.deleteLater()

    def _failed(self, message):
        if self.saved:
            message += " · showing saved statistics"
        self.status.emit(self.query.key, message)

    def close(self):
        self.cancel()
        self.cache.close()
