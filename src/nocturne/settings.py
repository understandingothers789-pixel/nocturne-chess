"""Validate persisted preferences before they cross into UI or search limits."""

import math

DEFAULTS = {
    "mode": "human_ai", "human_color": 1, "difficulty": "Intermediate",
    "seconds": 0, "increment": 0, "takebacks": True,
    "white_name": "White", "black_name": "Black", "white_engine": "custom", "black_engine": "custom",
    "theme": "Forest", "light": False, "coordinates": True, "animations": True, "overlays": True,
    "hash_mb": 32, "analysis_depth": 8, "analysis_seconds": 3.0,
    "external_path": "", "syzygy_path": "", "watch_delay_ms": 500,
}


def normalize(data) -> dict:
    data = data if isinstance(data, dict) else {}
    result = DEFAULTS.copy()
    choices = {"mode": ("human_ai", "human", "ai_ai", "analysis"), "human_color": (-1, 0, 1),
               "difficulty": ("Beginner", "Casual", "Intermediate", "Advanced", "Expert", "Maximum"),
               "theme": ("Forest", "Walnut", "Slate", "Midnight"),
               "white_engine": ("custom", "external"), "black_engine": ("custom", "external")}
    for key, options in choices.items():
        if data.get(key) in options:
            result[key] = data[key]
    for key in ("light", "coordinates", "animations", "overlays", "takebacks"):
        if isinstance(data.get(key), bool):
            result[key] = data[key]
    for key, minimum, maximum in (("hash_mb", 1, 256), ("analysis_depth", 1, 20),
                                   ("analysis_seconds", .1, 30), ("seconds", 0, 86400),
                                   ("increment", 0, 600), ("watch_delay_ms", 0, 3000)):
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            value = min(maximum, max(minimum, value))
            result[key] = float(value) if key == "analysis_seconds" else int(value)
    for key, limit in (("white_name", 80), ("black_name", 80), ("external_path", 4096), ("syzygy_path", 4096)):
        if isinstance(data.get(key), str):
            result[key] = data[key].strip()[:limit]
    return result
