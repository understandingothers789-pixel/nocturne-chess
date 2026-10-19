"""Stable position keys and engine-reported 1/2/5 node checkpoints."""

from hashlib import sha256


def position_key(game, node_id=None):
    node_id = game.current_node if node_id is None else node_id
    path = game.node_path(node_id)
    moves = " ".join(game.nodes[i].move.uci() for i in path[1:])
    return sha256((game.initial_fen + "\n" + moves).encode()).hexdigest()


def milestones(after, through):
    scale = 1_000_000
    while scale <= through:
        for multiple in (1, 2, 5):
            value = scale * multiple
            if after < value <= through:
                yield value
        scale *= 10


def node_label(nodes):
    for divisor, suffix in ((1_000_000_000, "B"), (1_000_000, "M")):
        if nodes >= divisor:
            return f"{nodes / divisor:g}{suffix}"
    return f"{nodes:,}"
