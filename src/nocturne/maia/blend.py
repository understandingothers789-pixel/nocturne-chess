"""Nocturne's explicitly defined comparison, not an official Maia statistic."""
import math


def move_quality(lines, uci):
    """Relative SF quality exp(-centipawn loss / 100), or unknown.

    Scores are raw UCI side-to-move centipawns. Bound/mate scores do not
    establish an exact centipawn loss, so they cannot enter this metric.
    """
    entries = list(lines.values())
    exact = [line for line in entries if line.get("score_type") == "cp"
             and line.get("bound", "exact") == "exact" and line.get("pv")]
    selected = next((line for line in exact if line["pv"][0] == uci), None)
    if selected is None or not exact or len(exact) != len(entries):
        return None, None
    best = max(line["score_value"] for line in exact)
    loss = max(0, best - selected["score_value"])
    return math.exp(-loss / 100), loss


def blend_score(probability, quality, engine_weight):
    if probability is None or quality is None:
        return None
    weight = max(0, min(1, engine_weight))
    return (1-weight) * probability + weight * quality
