"""JSON-lines worker for the official 79M checkpoint. No network at runtime."""

from collections import deque
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from . import RATINGS


def configuration():
    return SimpleNamespace(history=8, use_padding=True, include_time_info=False,
        dim_emb=128, dim_vit=1024, head_hid_dim=1024, num_blocks=8, num_heads=32,
        mlp_ratio=2.0, dropout=0.0, use_gab=True, use_relative_bias=False,
        use_absolute_pe=False, use_rms_norm=True, omit_qkv_biases=True,
        activation="gelu", gab_gen_size=128, gab_per_square_dim=32, gab_intermediate_dim=128)


class Predictor:
    def __init__(self, checkpoint):
        import torch
        # DirectML currently uses an older Torch without native RMSNorm.
        if not hasattr(torch.nn, "RMSNorm"):
            class RMSNorm(torch.nn.Module):
                def __init__(self, normalized_shape, eps=None, elementwise_affine=True):
                    super().__init__()
                    shape = (normalized_shape,) if isinstance(normalized_shape, int) else tuple(normalized_shape)
                    self.dims = tuple(range(-len(shape), 0))
                    self.eps = eps
                    self.weight = torch.nn.Parameter(torch.ones(shape)) if elementwise_affine else None

                def forward(self, x):
                    eps = self.eps if self.eps is not None else torch.finfo(x.dtype).eps
                    result = x * torch.rsqrt(x.pow(2).mean(self.dims, keepdim=True) + eps)
                    return result * self.weight if self.weight is not None else result
            torch.nn.RMSNorm = RMSNorm
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
        from .device import select_device
        self.device, self.device_label = select_device(torch)
        try:
            self.model.to(self.device)
        except Exception as exc:
            self._fallback(exc)
        self.indices = {move: i for i, move in enumerate(get_all_possible_moves())}

    def _fallback(self, exc):
        self.device = self.torch.device("cpu")
        self.model.to(self.device)
        self.device_label = f"CPU fallback · {str(exc)[:160]}"

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
        self.outcomes = {}
        if board.is_game_over():
            result = board.outcome()
            white = (1.0 if result.winner else 0.0) if result.winner is not None else 0.0
            draw = float(result.winner is None)
            self.outcomes = {str(r): [white, draw, 1-white-draw] for r in ratings}
            return {str(r): {} for r in ratings}
        tokens = get_historical_tokens(history, self.cfg, 180, 0, 180, 0)
        mask = get_legal_moves_mask(board, self.indices)
        def forward():
            with torch.inference_mode():
                elo = torch.tensor(ratings, dtype=torch.long, device=self.device)
                logits, values, _ = self.model(tokens.to(self.device).unsqueeze(0).expand(len(ratings), -1, -1), elo, elo)
                # Official Maia labels: side-to-move loss, draw, win.
                values = torch.softmax(values.float().cpu(), dim=-1).tolist()
                self.outcomes = {str(r): ([v[2], v[1], v[0]] if board.turn else v)
                                 for r, v in zip(ratings, values)}
                # Legal masking and normalization on CPU also support DirectML.
                return torch.softmax(logits.float().cpu().masked_fill(~mask.unsqueeze(0), float("-inf")), dim=-1)
        try:
            probabilities = forward()
        except Exception as exc:
            if self.device.type == "cpu":
                raise
            self._fallback(exc)
            probabilities = forward()
        return {str(rating): {m.uci(): float(probabilities[i, self.indices[
            m.uci() if board.turn else mirror_move(m.uci())]]) for m in legal}
            for i, rating in enumerate(ratings)}


def emit(value):
    print(json.dumps(value, allow_nan=False, separators=(",", ":")), flush=True)


def main():
    checkpoint = Path(sys.argv[1])
    try:
        predictor = Predictor(checkpoint)
        emit({"ready": True, "model": "Maia-3 79M", "device": predictor.device_label})
    except Exception as exc:
        emit({"error": f"Maia could not load: {exc}"})
        return 1
    for raw in sys.stdin:
        request = {}
        try:
            request = json.loads(raw)
            ratings = request["ratings"]
            if (not ratings or len(ratings) > len(RATINGS)
                    or len(set(ratings)) != len(ratings)
                    or any(type(r) is not int or r not in RATINGS for r in ratings)):
                raise ValueError("Invalid rating selection")
            # The selected rating is returned first; the sweep follows in small
            # batches so the GUI gets useful probabilities without waiting.
            for batch in ([ratings[0]], *[ratings[i:i+2] for i in range(1, len(ratings), 2)]):
                result = predictor.predict(request["root"], request["moves"], batch)
                emit({"id": request["id"], "policies": result, "outcomes": predictor.outcomes, "device": predictor.device_label, "complete": batch[-1] == ratings[-1]})
        except Exception as exc:
            emit({"id": request.get("id"), "error": str(exc)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
