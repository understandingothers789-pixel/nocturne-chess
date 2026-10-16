"""Interruptible, history-aware iterative alpha-beta search.

No null move, LMR, futility or other unmeasured selective pruning is enabled.
The transposition table verifies both position and reversible-history context.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
import time
from typing import Callable

from ..core.board import Board, Move
from .evaluate import evaluate, MG_VALUE

MATE = 30_000
MATE_THRESHOLD = 29_000
INF = 32_000
MAX_PLY = 96
MAX_QPLY = 20
_MASK64 = (1 << 64) - 1


@dataclass(frozen=True, slots=True)
class SearchLimits:
    depth: int = 6
    seconds: float = 1.0
    nodes: int | None = None
    hash_mb: int = 32
    use_tt: bool = True
    use_ordering: bool = True
    use_killers: bool = True
    use_pvs: bool = False
    mistake_cp: int = 0

    def __post_init__(self):
        if not 1 <= self.depth <= 64 or not 1 <= self.hash_mb <= 256:
            raise ValueError("Invalid depth or hash budget")
        if not math.isfinite(self.seconds) or self.seconds <= 0:
            raise ValueError("Search time must be positive and finite")
        if self.nodes is not None and self.nodes < 1:
            raise ValueError("Node budget must be positive")
        if not 0 <= self.mistake_cp <= 500:
            raise ValueError("Invalid move-selection margin")


@dataclass(frozen=True, slots=True)
class SearchInfo:
    depth: int
    seldepth: int
    score: int
    nodes: int
    seconds: float
    pv: tuple[Move, ...]
    hashfull: int = 0  # permille
    tbhits: int = 0

    @property
    def nps(self) -> int:
        return int(self.nodes / max(.001, self.seconds))


@dataclass(frozen=True, slots=True)
class SearchResult:
    best_move: Move | None
    info: SearchInfo
    stopped: bool = False
    claim_draw: bool = False


@dataclass(slots=True)
class TTEntry:
    key: int
    context: int
    halfmove: int
    depth: int
    score: int
    bound: int  # 0 exact, -1 upper, +1 lower
    move: Move | None


def _mix(key: int) -> int:
    key ^= key >> 30
    key = key * 0xBF58476D1CE4E5B9 & _MASK64
    key ^= key >> 27
    return key * 0x94D049BB133111EB & _MASK64


def _tt_score(score: int, ply: int, store: bool) -> int:
    adjustment = ply if store else -ply
    return score + adjustment if score > MATE_THRESHOLD else score - adjustment if score < -MATE_THRESHOLD else score


class SearchStopped(Exception):
    pass


class Searcher:
    def __init__(self, limits: SearchLimits | None = None, cancel: Callable[[], bool] | None = None):
        self.limits = limits or SearchLimits()
        self.cancel = cancel or (lambda: False)
        # A conservative budget for Python entry + Move objects and pointer array.
        capacity = 1 << max(8, (self.limits.hash_mb * 1024 * 1024 // 256).bit_length() - 1)
        self.table: list[TTEntry | None] = [None] * capacity
        self.tt_mask = capacity - 1
        self.tt_used = 0
        self.killers: list[list[Move]] = [[] for _ in range(MAX_PLY)]
        self.history: dict[tuple[int, int, int], int] = {}
        self.nodes = self.seldepth = 0
        self.started = self.deadline = 0.0
        self.context = 0

    def _visit(self, ply: int):
        if self.limits.nodes is not None and self.nodes >= self.limits.nodes:
            raise SearchStopped
        self.nodes += 1
        self.seldepth = max(self.seldepth, ply)
        if self.nodes == 1 or self.nodes & 15 == 0:
            if self.cancel() or time.perf_counter() >= self.deadline:
                raise SearchStopped

    def _ordered(self, board: Board, moves: list[Move], tt_move: Move | None, ply: int) -> list[Move]:
        if not self.limits.use_ordering:
            return moves

        def value(move: Move):
            if move == tt_move:
                return 10_000_000
            attacker = abs(board.cells[move.from_sq])
            score = 0
            if board.is_capture(move):
                victim = abs(board.cells[move.to_sq]) or 1
                score += 1_000_000 + MG_VALUE[victim] * 16 - MG_VALUE[attacker]
            if move.promotion:
                score += 900_000 + MG_VALUE[move.promotion]
            if self.limits.use_killers and ply < MAX_PLY and move in self.killers[ply]:
                score += 500_000 - self.killers[ply].index(move)
            return score + self.history.get((board.turn, move.from_sq, move.to_sq), 0)

        return sorted(moves, key=value, reverse=True)

    def _push(self, board: Board, move: Move) -> int:
        old = self.context
        board.push(move)
        self.context = _mix(board.key) if board.halfmove == 0 else (old + _mix(board.key)) & _MASK64
        return old

    def _pop(self, board: Board, context: int):
        board.pop()
        self.context = context

    @staticmethod
    def _draw(board: Board) -> bool:
        # Search assumes a rational losing side takes an available claim. The
        # public game model still requires a deliberate claim action.
        return board.halfmove >= 100 or board.repetition_count() >= 3 or board.insufficient_material()

    def _quiescence(self, board: Board, alpha: int, beta: int, ply: int, qply: int) -> tuple[int, list[Move]]:
        self._visit(ply)
        check = board.in_check()
        legal = list(board.legal_moves())
        if not legal:
            return (-MATE + ply if check else 0), []
        if self._draw(board):
            return 0, []
        if ply >= MAX_PLY - 1 or qply >= MAX_QPLY:
            return evaluate(board), []
        best, pv = -INF, []
        if not check:
            best = evaluate(board)
            if best >= beta:
                return best, []
            alpha = max(alpha, best)
            legal = [m for m in legal if board.is_capture(m) or m.promotion]
        for move in self._ordered(board, legal, None, ply):
            context = self._push(board, move)
            try:
                child, line = self._quiescence(board, -beta, -alpha, ply + 1, qply + 1)
                score = -child
            finally:
                self._pop(board, context)
            if score > best:
                best, pv = score, [move] + line
            alpha = max(alpha, score)
            if alpha >= beta:
                break
        return best, pv

    def _negamax(self, board: Board, depth: int, alpha: int, beta: int, ply: int) -> tuple[int, list[Move]]:
        if depth <= 0:
            return self._quiescence(board, alpha, beta, ply, 0)
        self._visit(ply)
        legal = list(board.legal_moves())
        if not legal:
            return (-MATE + ply if board.in_check() else 0), []
        if self._draw(board):
            return 0, []
        if ply >= MAX_PLY - 1:
            return evaluate(board), []
        original_alpha = alpha
        entry = self.table[board.key & self.tt_mask] if self.limits.use_tt else None
        tt_move = entry.move if entry and entry.key == board.key and entry.move in legal else None
        if entry and entry.key == board.key and entry.context == self.context and entry.halfmove == board.halfmove:
            if entry.depth >= depth:
                score = _tt_score(entry.score, ply, False)
                if entry.bound == 0 or (entry.bound == 1 and score >= beta) or (entry.bound == -1 and score <= alpha):
                    return score, [tt_move] if tt_move else []
        best, best_move, pv = -INF, None, []
        for index, move in enumerate(self._ordered(board, legal, tt_move, ply)):
            quiet = not board.is_capture(move) and not move.promotion
            context = self._push(board, move)
            try:
                if self.limits.use_pvs and index > 0:
                    child, line = self._negamax(board, depth - 1, -alpha - 1, -alpha, ply + 1)
                    score = -child
                    if alpha < score < beta:
                        child, line = self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
                        score = -child
                else:
                    child, line = self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
                    score = -child
            finally:
                self._pop(board, context)
            if score > best:
                best, best_move, pv = score, move, [move] + line
            alpha = max(alpha, score)
            if alpha >= beta:
                if quiet and self.limits.use_ordering:
                    if self.limits.use_killers and move not in self.killers[ply]:
                        self.killers[ply] = [move] + self.killers[ply][:1]
                    key = (board.turn, move.from_sq, move.to_sq)
                    self.history[key] = min(100_000, self.history.get(key, 0) + depth * depth)
                break
        if self.limits.use_tt:
            slot = board.key & self.tt_mask
            previous = self.table[slot]
            if previous is None:
                self.tt_used += 1
            bound = -1 if best <= original_alpha else 1 if best >= beta else 0
            self.table[slot] = TTEntry(board.key, self.context, board.halfmove, depth,
                                       _tt_score(best, ply, True), bound, best_move)
        return best, pv

    def search(self, position: Board, on_info: Callable[[SearchInfo], None] | None = None) -> SearchResult:
        board = position.copy()
        self.nodes = self.seldepth = 0
        self.started = time.perf_counter()
        self.deadline = self.started + self.limits.seconds
        self.context = sum(_mix(k) for k in board.key_history[-(board.halfmove + 1):]) & _MASK64
        legal = list(board.legal_moves())
        outcome = board.outcome(legal)
        if outcome:
            score = -MATE if outcome.winner else 0
            return SearchResult(None, SearchInfo(0, 0, score, 0, time.perf_counter() - self.started, ()))
        if board.claimable_draws():
            return SearchResult(None, SearchInfo(0, 0, 0, 0, time.perf_counter() - self.started, ()), claim_draw=True)
        best = legal[0]
        completed = SearchInfo(0, 0, evaluate(board), 0, time.perf_counter() - self.started, (best,))
        stopped = False
        root_scores: list[tuple[int, Move, tuple[Move, ...]]] = []
        try:
            for depth in range(1, self.limits.depth + 1):
                if self.cancel() or time.perf_counter() >= self.deadline:
                    raise SearchStopped
                alpha, iteration_best, iteration_pv = -INF, best, (best,)
                iteration_scores = []
                for move in self._ordered(board, legal, best, 0):
                    context = self._push(board, move)
                    try:
                        # Weak levels require comparable, exact root scores.
                        window_alpha = -INF if self.limits.mistake_cp else alpha
                        child, line = self._negamax(board, depth - 1, -INF, -window_alpha, 1)
                        score = -child
                    finally:
                        self._pop(board, context)
                    iteration_scores.append((score, move, tuple([move] + line)))
                    if score > alpha:
                        alpha, iteration_best, iteration_pv = score, move, tuple([move] + line)
                best, root_scores = iteration_best, iteration_scores
                completed = SearchInfo(depth, self.seldepth, alpha, self.nodes,
                                       time.perf_counter() - self.started, iteration_pv,
                                       self.tt_used * 1000 // len(self.table))
                if on_info:
                    on_info(completed)
                if abs(alpha) > MATE_THRESHOLD:
                    break
        except SearchStopped:
            stopped = True
        if self.limits.mistake_cp and root_scores and abs(completed.score) < MATE_THRESHOLD:
            candidates = sorted(root_scores, key=lambda item: item[0], reverse=True)
            candidates = [item for item in candidates if item[0] >= completed.score - self.limits.mistake_cp][:4]
            chosen = random.Random(board.key ^ completed.depth).choice(candidates)
            score, best, pv = chosen
            completed = SearchInfo(completed.depth, completed.seldepth, score, completed.nodes,
                                   completed.seconds, pv, completed.hashfull)
        final = SearchInfo(completed.depth, self.seldepth, completed.score, self.nodes,
                           time.perf_counter() - self.started, completed.pv,
                           self.tt_used * 1000 // len(self.table))
        return SearchResult(best, final, stopped)


DIFFICULTIES = {
    "Beginner": (1, .12, 180), "Casual": (2, .25, 70),
    "Intermediate": (3, .7, 0), "Advanced": (4, 1.5, 0),
    "Expert": (6, 3.0, 0), "Maximum": (20, 6.0, 0),
}


def difficulty_limits(name: str, hash_mb=32, available: float | None = None, increment=0.0) -> SearchLimits:
    depth, seconds, mistake = DIFFICULTIES.get(name, DIFFICULTIES["Intermediate"])
    if available is not None:
        seconds = min(seconds, max(.005, min(available * .08 + increment * .6, available - .08)))
    return SearchLimits(depth=depth, seconds=seconds, hash_mb=hash_mb, mistake_cp=mistake)


def score_text(score: int) -> str:
    if abs(score) > MATE_THRESHOLD:
        moves = max(0, (MATE - abs(score) + 1) // 2)
        return f"{'−' if score < 0 else ''}M{moves}"
    return f"{score / 100:+.2f}"
