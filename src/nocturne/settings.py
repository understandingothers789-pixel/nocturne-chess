"""Validate persisted preferences before they cross into UI or search limits."""

import math

DEFAULTS = {
    "mode": "analysis",
    "human_color": 1,
    "difficulty": "Intermediate",
    "seconds": 0,
    "increment": 0,
    "takebacks": True,
    "white_name": "White",
    "black_name": "Black",
    "white_engine": "external",
    "black_engine": "external",
    "theme": "Classic",
    "piece_set": "Nibbler",
    "piece_set_version": 1,
    "appearance_version": 1,
    "light": False,
    "coordinates": True,
    "show_clocks": True,
    "show_raw_pgn": False,
    "expand_pv": False,
    "wheel_game_moves": True,
    "wheel_analysis_moves": True,
    "animations": True,
    "overlays": True,
    "hash_mb": 32,
    "analysis_depth": 24,
    "analysis_seconds": 3.0,
    "review_seconds": 3.0,
    "details": False,
    "smart_move": True,
    "candidate_style": "lines",
    "candidate_marker_version": 1,
    "branch_arrows": True,
    "layout": "classic",
    "analysis_kind": "infinite",
    "multipv": 1,
    "analysis_menu_version": 1,
    "explorer_enabled": False,
    "explorer_source": "masters",
    "explorer_speed": "all",
    "explorer_rating": 0,
    "engine_id": "",
    "analysis_nodes": 0,
    "external_path": "",
    "syzygy_path": "",
    "watch_delay_ms": 500,
}


def normalize(data) -> dict:
    data = data if isinstance(data, dict) else {}
    result = DEFAULTS.copy()
    choices = {
        "mode": ("human_ai", "human", "ai_ai", "analysis"),
        "human_color": (-1, 0, 1),
        "difficulty": ("Beginner", "Casual", "Intermediate", "Advanced", "Expert", "Maximum"),
        "layout": ("classic", "analysis-left"),
        "analysis_kind": ("infinite", "explore", "bounded"),
        "candidate_style": ("arrows", "lines"),
        "explorer_source": ("masters", "lichess", "chessdb"),
        "explorer_speed": ("all", "ultraBullet", "bullet", "blitz", "rapid", "classical", "correspondence"),
        "explorer_rating": (0, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500),
        "theme": ("Classic", "Grey", "Walnut", "Slate", "Forest", "Midnight"),
        "piece_set": ("Nibbler", "Cburnett", "Original"),
        "white_engine": ("custom", "external"),
        "black_engine": ("custom", "external"),
    }
    for key, options in choices.items():
        if key == "explorer_rating" and type(data.get(key)) is not int:
            continue
        if data.get(key) in options:
            result[key] = data[key]
    # Upgrade the old default once; later explicit palette choices are retained.
    if data.get("appearance_version") != 1 and data.get("theme", "Forest") == "Forest":
        result["theme"] = "Classic"
    if data.get("piece_set_version") != 1:
        result["piece_set"] = "Nibbler"
    if data.get("candidate_marker_version") != 1:
        result["candidate_style"] = "lines"
    for key in (
        "light",
        "coordinates",
        "show_clocks",
        "show_raw_pgn",
        "expand_pv",
        "wheel_game_moves",
        "wheel_analysis_moves",
        "animations",
        "overlays",
        "takebacks",
        "smart_move",
        "branch_arrows",
        "details",
        "explorer_enabled",
    ):
        if isinstance(data.get(key), bool):
            result[key] = data[key]
    for key, minimum, maximum in (
        ("hash_mb", 1, 65536),
        ("analysis_depth", 1, 128),
        ("multipv", 1, 32),
        ("analysis_nodes", 0, 2_000_000_000),
        ("analysis_seconds", 0.05, 600),
        ("review_seconds", 0.05, 600),
        ("seconds", 0, 86400),
        ("increment", 0, 600),
        ("watch_delay_ms", 0, 3000),
    ):
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            value = min(maximum, max(minimum, value))
            result[key] = float(value) if key in ("analysis_seconds", "review_seconds") else int(value)
    for key, limit in (
        ("engine_id", 128),
        ("white_name", 80),
        ("black_name", 80),
        ("external_path", 4096),
        ("syzygy_path", 4096),
    ):
        if isinstance(data.get(key), str):
            result[key] = data[key].strip()[:limit]
    # Older Live/Bounded modes always searched one PV despite the stored spin value.
    if data.get("analysis_menu_version") != 1 and data.get("analysis_kind") in ("infinite", "bounded"):
        result["multipv"] = 1
    return result
