"""Ordered move trees; child zero is the main continuation, never overwritten."""

from dataclasses import dataclass, field

from .board import Move
from .rules import Board


@dataclass(slots=True)
class Node:
    parent: int | None
    move: Move | None
    san: str = ""
    depth: int = 0
    children: list[int] = field(default_factory=list)
    clock: dict[int, float] = field(default_factory=lambda: {1: 0, -1: 0})
    evaluation: int | None = None
    comment: str = ""
    starting_comment: str = ""
    nags: list[int] = field(default_factory=list)
    analysis: dict = field(default_factory=dict)


def build_nodes(initial_fen, edges):
    """Validate every variation with reversible DFS, without recursive depth limits."""
    from .notation import san

    if len(edges) > 20_000:
        raise ValueError("Move tree exceeds 20,000 nodes")
    nodes = [Node(None, None)]
    for index, (parent, move) in enumerate(edges, 1):
        if type(parent) is not int or not 0 <= parent < index:
            raise ValueError("Invalid variation parent")
        if any(nodes[c].move == move for c in nodes[parent].children):
            raise ValueError("Duplicate variation move")
        nodes.append(Node(parent, move, depth=nodes[parent].depth + 1))
        nodes[parent].children.append(index)
    board = Board(initial_fen)
    stack = [(False, c) for c in reversed(nodes[0].children)]
    while stack:
        exiting, index = stack.pop()
        if exiting:
            board.pop()
            continue
        node = nodes[index]
        legal = list(board.legal_moves())
        if node.move not in legal or board.outcome():
            raise ValueError(f"Illegal variation move at node {index}")
        node.san = san(board, node.move, legal)
        board.push(node.move)
        stack.append((True, index))
        stack.extend((False, c) for c in reversed(node.children))
    return nodes


def mainline(nodes, start=0):
    ids = [start]
    while nodes[ids[-1]].children:
        ids.append(nodes[ids[-1]].children[0])
    return ids


def tree_tokens(nodes, initial_fen):
    """PGN order, with node links and unlinked parentheses for the GUI."""
    root = Board(initial_fen)
    output, stack = [], [("expand", 0)]
    while stack:
        kind, index = stack.pop()
        if kind in ("(", ")"):
            output.append((kind, None))
        elif kind == "move":
            node = nodes[index]
            offset = node.depth - 1 + (root.turn == -1)
            number = root.fullmove + offset // 2
            output.append((f"{number}{'...' if offset % 2 else '.'} {node.san}", index))
        elif nodes[index].children:
            first, *others = nodes[index].children
            tasks = [("move", first)]
            for child in others:
                tasks.extend([("(", 0), ("move", child), ("expand", child), (")", 0)])
            tasks.append(("expand", first))
            stack.extend(reversed(tasks))
    return output


def ordered_edges(nodes):
    """Renumber in preorder so exported child order includes main-line promotions."""
    remap, edges = {0: 0}, []
    stack = list(reversed(nodes[0].children))
    while stack:
        index = stack.pop()
        node = nodes[index]
        edges.append((remap[node.parent], node.move))
        remap[index] = len(edges)
        stack.extend(reversed(node.children))
    return edges
