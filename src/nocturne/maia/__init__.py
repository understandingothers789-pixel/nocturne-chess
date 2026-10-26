"""Local Maia-3 policy inference, isolated from Stockfish and the Qt thread."""

RATINGS = tuple(range(600, 3001, 200))
MODEL_REVISION = "a107d6ceb7b298cb04ae1da4edffe2939858b894"
MODEL_URL = f"https://huggingface.co/UofTCSSLab/Maia3-79M/resolve/{MODEL_REVISION}/maia3-79m.pt"
MODEL_NAME = "Maia-3 79M"


def percentage(value):
    if value is None:
        return "—"
    percent = value * 100
    return f"{percent:.1f}%" if percent >= 0.1 else f"{percent:.3g}%"
