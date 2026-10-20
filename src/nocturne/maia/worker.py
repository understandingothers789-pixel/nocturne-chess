"""JSON-lines worker for the official 79M checkpoint. No network at runtime."""

from collections import deque
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace


def configuration():
    return SimpleNamespace(history=8, use_padding=True, include_time_info=False,
        dim_emb=128, dim_vit=1024, head_hid_dim=1024, num_blocks=8, num_heads=32,
        mlp_ratio=2.0, dropout=0.0, use_gab=True, use_relative_bias=False,
        use_absolute_pe=False, use_rms_norm=True, omit_qkv_biases=True,
        activation="gelu", gab_gen_size=128, gab_per_square_dim=32, gab_intermediate_dim=128)


class Predictor:
    def __init__(self, checkpoint):
        import torch
        from .vendor.models import MAIA3Model
        from .vendor.utils import get_all_possible_moves
        torch.set_num_threads(max(1, min(4, (os.cpu_count() or 2) // 2)))
        self.torch = torch
        self.cfg = configuration()
        self.model = MAIA3Model(self.cfg)
        saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
        weights = saved.get("model_state_dict", saved)
        weights = {k.replace("smolgen", "gab"): v for k, v in weights.items()}
        self.model.load_state_dict(weights, strict=True)
        self.model.eval()
        self.indices = {move: i for i, move in enumerate(get_all_possible_moves())}

    def predict(self, root, moves, ratings):
        import chess
        from .vendor.dataset import tokenize_board, get_historical_tokens, get_legal_moves_mask
        from .vendor.utils import mirror_move
        torch = self.torch
        board = chess.Board(root)
        history = deque([tokenize_board(board)], maxlen=8)
        for uci in moves:
            board.push_uci(uci)
            history.append(tokenize_board(board))
        legal = list(board.legal_moves)
        if board.is_game_over():
            return {str(r): {} for r in ratings}
        tokens = get_historical_tokens(history, self.cfg, 180, 0, 180, 0)
        mask = get_legal_moves_mask(board, self.indices)
        with torch.inference_mode():
            elo = torch.tensor(ratings, dtype=torch.long)
            logits, _, _ = self.model(tokens.unsqueeze(0).expand(len(ratings), -1, -1), elo, elo)
            probabilities = torch.softmax(logits.float().masked_fill(~mask.unsqueeze(0), float("-inf")), dim=-1)
        return {str(rating): {m.uci(): float(probabilities[i, self.indices[
            m.uci() if board.turn else mirror_move(m.uci())]]) for m in legal}
            for i, rating in enumerate(ratings)}


def emit(value):
    print(json.dumps(value, allow_nan=False, separators=(",", ":")), flush=True)


def main():
    checkpoint = Path(sys.argv[1])
    try:
        predictor = Predictor(checkpoint)
        emit({"ready": True, "model": "Maia-3 79M"})
    except Exception as exc:
        emit({"error": f"Maia could not load: {exc}"})
        return 1
    for raw in sys.stdin:
        request = {}
        try:
            request = json.loads(raw)
            ratings = request["ratings"]
            if not ratings or len(ratings) > 14 or any(type(r) is not int or not 400 <= r <= 3000 for r in ratings):
                raise ValueError("Invalid rating selection")
            # The selected rating is returned first; the sweep follows in small
            # batches so the GUI gets useful probabilities without waiting.
            for batch in ([ratings[0]], *[ratings[i:i+2] for i in range(1, len(ratings), 2)]):
                result = predictor.predict(request["root"], request["moves"], batch)
                emit({"id": request["id"], "policies": result, "complete": batch[-1] == ratings[-1]})
        except Exception as exc:
            emit({"id": request.get("id"), "error": str(exc)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
