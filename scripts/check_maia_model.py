"""Small real-checkpoint smoke check: legal probabilities and rating conditioning."""
import json
from pathlib import Path
import subprocess
import sys

import chess
from nocturne.maia.worker import Predictor


def main():
    checkpoint = Path(sys.argv[1])
    if len(sys.argv) > 2:
        request = {"id": 1, "root": chess.STARTING_FEN, "moves": ["e2e4"], "ratings": [1800, 2000]}
        run = subprocess.run([sys.argv[2], str(checkpoint)], input=json.dumps(request)+"\n",
                             capture_output=True, text=True, timeout=120, check=True)
        messages = [json.loads(line) for line in run.stdout.splitlines()]
        result = {k: v for msg in messages for k, v in msg.get("policies", {}).items()}
        assert len(result) == 2
        assert all(abs(sum(p.values()) - 1) < 1e-5 for p in result.values())
        print("Packaged Maia worker: real 79M predictions passed")
        return
    predictor = Predictor(checkpoint)
    for root, moves in [(chess.STARTING_FEN, []), (chess.STARTING_FEN, ["e2e4"]),
                        ("7k/8/8/8/8/8/1p6/7K b - - 0 1", [])]:
        board = chess.Board(root)
        for move in moves:
            board.push_uci(move)
        policies = predictor.predict(root, moves, [600, 1800, 3000])
        legal = {m.uci() for m in board.legal_moves}
        for policy in policies.values():
            assert set(policy) == legal
            assert abs(sum(policy.values()) - 1) < 1e-5
            assert all(0 <= p <= 1 for p in policy.values())
        assert policies['600'] != policies['3000']
    print("Official 79M model: White, Black, underpromotions and rating conditioning passed")


if __name__ == "__main__":
    main()
