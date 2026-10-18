"""Engine-evidenced move review; percentages are estimates, not site ratings."""

import math

from .core.notation import san
from .core.rules import Board

MODEL = "nocturne-accuracy-v1"
LABELS = ("Best", "Excellent", "Good", "Inaccuracy", "Mistake", "Blunder")
ERRORS = frozenset(("Inaccuracy", "Mistake", "Blunder"))
CRITERIA = (
    "Nocturne v1 estimate: chance-loss bands 3/8/20 pp; arithmetic-mean accuracy; "
    "same-root equal-limit searches, depths may differ; mate distance not graded."
)


def chance(info):
    """A score-to-outcome proxy, never presented as an observed win probability."""
    if not isinstance(info, dict) or info.get("bound", "exact") != "exact":
        return None
    value = info.get("score_value")
    if type(value) is not int:
        return None
    if info.get("score_type") == "cp":
        return 50 + 50 * math.tanh(0.00184104 * max(-100000, min(100000, value)))
    if info.get("score_type") == "mate" and value:
        return 100.0 if value > 0 else 0.0
    return None


def classify(position, move, best, played, context=None):
    """Both scores must describe legal first moves from the SAME mover/root."""
    before, after = chance(best), chance(played)
    if before is None or after is None:
        return None
    try:
        best_move = position.parse_uci(best["pv"][0])
        played_move = position.parse_uci(played["pv"][0])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if played_move != move:
        return None
    loss = max(0.0, before - after)
    is_best = best_move == move
    if is_best:
        loss = 0.0
    accuracy = min(100.0, max(0.0, 103.1668100711649 * math.exp(-0.04354415386753951 * loss)
                                - 3.166924740191411 + 1))
    label = ("Best" if is_best else "Blunder" if loss >= 20 else "Mistake" if loss >= 8
             else "Inaccuracy" if loss >= 3 else "Good" if loss >= 1 else "Excellent")
    record = {
        "model": MODEL, "root_fen": position.fen(), "move": move.uci(),
        "label": label, "accuracy": accuracy, "loss_percent": loss,
        "best_chance": before, "played_chance": after,
        "best_uci": best_move.uci(), "best_san": san(position, best_move),
        "best": dict(best), "played": dict(played), "criteria": CRITERIA,
        "context": dict(context) if isinstance(context, dict) else {},
    }
    if best["score_type"] == played["score_type"] == "cp":
        record["loss_cp"] = max(0, best["score_value"] - played["score_value"])
    return record


def rows(game):
    """Revalidate saved evidence against the selected line; never reuse a sibling's score."""
    position = Board(game.initial_fen)
    records = game.metadata.get("review", {})
    records = records if isinstance(records, dict) else {}
    result = []
    for node_id in game._line_nodes[1:]:
        node = game.nodes[node_id]
        saved = records.get(str(node_id), {})
        record = None
        if (isinstance(saved, dict) and saved.get("model") == MODEL
                and saved.get("root_fen") == position.fen() and saved.get("move") == node.move.uci()):
            record = classify(position, node.move, saved.get("best"), saved.get("played"), saved.get("context"))
        result.append({"node": node_id, "san": node.san, "color": position.turn,
                       "number": position.fullmove, "record": record})
        position.push(node.move)
    return result


def summarize(entries, color=None):
    selected = [e for e in entries if color is None or e["color"] == color]
    scored = [e["record"] for e in selected if e["record"] is not None]
    return {
        "total": len(selected), "reviewed": len(scored),
        "accuracy": sum(r["accuracy"] for r in scored) / len(scored) if scored else None,
        "counts": {label: sum(r["label"] == label for r in scored) for label in LABELS},
    }
