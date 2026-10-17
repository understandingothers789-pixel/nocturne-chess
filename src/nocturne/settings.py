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
    "theme": "Forest",
    "light": False,
    "coordinates": True,
    "animations": True,
    "overlays": True,
    "hash_mb": 32,
    "analysis_depth": 24,
    "analysis_seconds": 3.0,
    "details": False,
    "smart_move": True,
    "smart_all": False,
    "branch_arrows": True,
    "layout": "classic",
    "analysis_kind": "infinite",
    "multipv": 3,
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
        "theme": ("Forest", "Walnut", "Slate", "Midnight"),
        "white_engine": ("custom", "external"),
        "black_engine": ("custom", "external"),
    }
    for key, options in choices.items():
        if data.get(key) in options:
            result[key] = data[key]
    for key in (
        "light",
        "coordinates",
        "animations",
        "overlays",
        "takebacks",
        "smart_move",
        "smart_all",
        "branch_arrows",
        "details",
    ):
        if isinstance(data.get(key), bool):
            result[key] = data[key]
    for key, minimum, maximum in (
        ("hash_mb", 1, 65536),
        ("analysis_depth", 1, 128),
        ("multipv", 1, 32),
        ("analysis_nodes", 0, 2_000_000_000),
        ("analysis_seconds", 0.05, 600),
        ("seconds", 0, 86400),
        ("increment", 0, 600),
        ("watch_delay_ms", 0, 3000),
    ):
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            value = min(maximum, max(minimum, value))
            result[key] = float(value) if key == "analysis_seconds" else int(value)
    for key, limit in (
        ("engine_id", 128),
        ("white_name", 80),
        ("black_name", 80),
        ("external_path", 4096),
        ("syzygy_path", 4096),
    ):
        if isinstance(data.get(key), str):
            result[key] = data[key].strip()[:limit]
    return result
