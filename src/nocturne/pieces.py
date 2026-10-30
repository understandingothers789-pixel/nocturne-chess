"""One registry for scalable chess-piece SVGs and their filename conventions.

Every registered style uses the same Qt SVG renderer. To add a style, provide
twelve licensed w/b + p/n/b/r/q/k SVGs and register its directory and casing.
The SVG viewBox owns its whitespace; the renderer adds no rasterizing or inset.
"""

from dataclasses import dataclass
from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parent / "assets" / "pieces"


@dataclass(frozen=True)
class PieceSet:
    directory: Path
    uppercase_codes: bool = False


PIECE_SETS = {
    "Nibbler": PieceSet(ASSET_ROOT / "nibbler" / "source", uppercase_codes=True),
    "Lichess": PieceSet(ASSET_ROOT),
    "Neo": PieceSet(ASSET_ROOT / "neo"),
}
PIECE_SET_NAMES = tuple(PIECE_SETS)
DEFAULT_PIECE_SET = "Nibbler"


def piece_path(style: str, piece: int, piece_chars: str) -> Path:
    """Resolve a registered vector using its canonical color/type filename."""
    # Keep old saved studies and appearance previews readable after the style
    # picker was simplified to Lichess and Nibbler.
    style = {"Cburnett": "Lichess", "Original": DEFAULT_PIECE_SET}.get(style, style)
    descriptor = PIECE_SETS.get(style, PIECE_SETS[DEFAULT_PIECE_SET])
    kind = piece_chars[abs(piece)].lower()
    if descriptor.uppercase_codes:
        kind = kind.upper()
    return descriptor.directory / (("w" if piece > 0 else "b") + kind + ".svg")
