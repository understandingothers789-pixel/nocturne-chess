"""Human choice probabilities grouped by exact, side-to-move Stockfish loss."""
import math


def assess_moves(policy, lines):
    """Keep unsearched/bound/mate moves unknown; never renormalize coverage.

    The 50/150 cp boundaries match Maia Platform's centipawn fallback.
    Loss is relative to the best available exact searched move, not a claim
    that every legal move has been evaluated. Raw UCI scores already use the
    current player's perspective for both White and Black.
    """
    exact = {}
    has_mate = False
    for line in lines.values():
        if not line.get("pv") or line.get("bound", "exact") != "exact":
            continue
        if line.get("score_type") == "mate":
            has_mate = True
        score = line.get("score_value")
        if line.get("score_type") != "cp" or type(score) not in (int, float) or not math.isfinite(score):
            continue
        uci = line["pv"][0]
        previous = exact.get(uci)
        if previous is None or (line.get("depth", 0), line.get("nodes", 0)) >= (
                previous.get("depth", 0), previous.get("nodes", 0)):
            exact[uci] = line
    best = max((line["score_value"] for line in exact.values()), default=None)
    results = {}
    for uci, probability in policy.items():
        if type(probability) not in (int, float) or not math.isfinite(probability) or not 0 <= probability <= 1:
            continue
        line = exact.get(uci)
        loss = max(0, best - line["score_value"]) if best is not None and line and not has_mate else None
        category = "unknown" if loss is None else "best" if loss <= 50 else "ok" if loss <= 150 else "blunder"
        results[uci] = {"probability": probability, "loss": loss, "category": category}
    return results
