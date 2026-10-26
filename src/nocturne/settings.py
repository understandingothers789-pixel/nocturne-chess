"""Validate persisted preferences before they cross into UI or search limits."""

import math
from .maia import RATINGS as MAIA_RATINGS
from .pieces import DEFAULT_PIECE_SET, PIECE_SET_NAMES

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
    "piece_set": DEFAULT_PIECE_SET,
    "piece_set_version": 1,
    "appearance_version": 1,
    "light": False,
    "coordinates": True,
    "show_clocks": True,
    "maia_enabled": True,
    "maia_rating": 1800,
    "maia_device": "auto",
    "show_maia_insights": True,
    "maia_arrows": True,
    "maia_arrow_count": 3,
    "maia_blend_weight": 50,
    "show_raw_pgn": False,
    "raw_pgn_version": 1,
    "expand_pv": False,
    "expand_pv_version": 2,
    "cursor_preview": True,
    "cursor_preview_version": 1,
    "wheel_game_moves": True,
    "wheel_analysis_moves": True,
    "animations": False,
    "animation_version": 1,
    "overlays": True,
    "show_eval_graph": True,
    "hash_mb": 32,
    "analysis_depth": 128,
    "analysis_seconds": 600.0,
    "review_seconds": 3.0,
    "review_confirm": True,
    "analysis_snapshots": False,
    "details": False,
    "show_seldepth": False,
    "smart_move": True,
    "candidate_style": "lines",
    "candidate_marker_version": 1,
    "branch_arrows": True,
    "layout": "classic",
    "analysis_kind": "nodes",
    "multipv": 1,
    "analysis_menu_version": 1,
    "explorer_enabled": False,
    "explorer_enabled_version": 1,
    "explorer_statistics": False,
    "explorer_source": "chessdb",
    "explorer_speed": "all",
    "explorer_rating": 0,
    "engine_id": "",
    "analysis_nodes": 1_000_000_000,
    "analysis_limit_version": 2,
    "auto_eval_nodes": 200_000_000,
    "auto_eval_limit_version": 2,
    "auto_play_nodes": 10_000_000,
    "reanalyze_on_navigation": False,
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
        "maia_rating": MAIA_RATINGS,
        "maia_device": ("auto", "cpu"),
        "maia_arrow_count": (1, 3, 5),
        "difficulty": ("Beginner", "Casual", "Intermediate", "Advanced", "Expert", "Maximum"),
        "layout": ("classic", "analysis-left"),
        "analysis_kind": ("infinite", "explore", "bounded", "nodes"),
        "candidate_style": ("arrows", "lines"),
        "explorer_source": ("masters", "lichess", "chessdb"),
        "explorer_speed": ("all", "ultraBullet", "bullet", "blitz", "rapid", "classical", "correspondence"),
        "explorer_rating": (0, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500),
        "theme": ("Classic", "Grey", "Walnut", "Slate", "Forest", "Midnight"),
        "piece_set": PIECE_SET_NAMES,
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
        result["piece_set"] = DEFAULT_PIECE_SET
    if data.get("candidate_marker_version") != 1:
        result["candidate_style"] = "lines"
    # A saved source from the older UI remains selected even if its panel was
    # hidden. New installs stay offline; the new explicit opt-out is respected.
    if "explorer_statistics" not in data:
        result["explorer_statistics"] = (data.get("explorer_enabled") is True
                                         or data.get("explorer_source") in choices["explorer_source"])
    for key in (
        "light",
        "coordinates",
        "show_clocks",
        "show_raw_pgn",
        "maia_enabled",
        "maia_arrows",
        "show_maia_insights",
        "expand_pv",
        "cursor_preview",
        "wheel_game_moves",
        "wheel_analysis_moves",
        "animations",
        "overlays",
        "show_eval_graph",
        "takebacks",
        "smart_move",
        "branch_arrows",
        "details",
        "show_seldepth",
        "explorer_enabled",
        "explorer_statistics",
        "reanalyze_on_navigation",
        "review_confirm",
        "analysis_snapshots",
    ):
        if isinstance(data.get(key), bool):
            result[key] = data[key]
    # Prefer instant placement, including profiles saved with the old default.
    if data.get("animation_version") != 1:
        result["animations"] = False
    # The database explorer used to be enabled in some saved profiles. Make
    # the new opt-in default consistent on the first run after this change.
    if data.get("explorer_enabled_version") != 1:
        result["explorer_enabled"] = False
    if data.get("raw_pgn_version") != 1:
        result["show_raw_pgn"] = False
    # Older builds could preserve the global expand-all setting. Reset it once
    # to the compact default, then respect later explicit user choices.
    if data.get("expand_pv_version") != 2:
        result["expand_pv"] = False
    # Adopt the cursor board once for older profiles, then preserve opt-outs.
    if data.get("cursor_preview_version") != 1:
        result["cursor_preview"] = True
    for key, minimum, maximum in (
        ("maia_blend_weight", 0, 100),
        ("hash_mb", 1, 65536),
        ("analysis_depth", 1, 128),
        ("multipv", 1, 32),
        ("analysis_nodes", 0, 2_000_000_000),
        ("auto_eval_nodes", 0, 2_000_000_000),
        ("auto_play_nodes", 1, 2_000_000_000),
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
    # Give existing installs the new useful node-based defaults once.
    if data.get("analysis_limit_version") not in (1, 2):
        if data.get("analysis_kind") == "infinite":
            result["analysis_kind"] = "bounded"
        if data.get("analysis_nodes", 0) == 0:
            result["analysis_nodes"] = 1_000_000_000
        if data.get("analysis_depth", 24) == 24:
            result["analysis_depth"] = 128
        if data.get("analysis_seconds", 3.0) == 3.0:
            result["analysis_seconds"] = 600.0
    # The old default also imposed a hidden ten-minute/depth limit. Use a
    # true node-only search for that default; keep explicitly customized limits.
    if (data.get("analysis_limit_version") != 2 and result["analysis_kind"] == "bounded"
            and result["analysis_depth"] == 128 and result["analysis_seconds"] == 600
            and result["analysis_nodes"]):
        result["analysis_kind"] = "nodes"
    if result["analysis_kind"] == "nodes" and not result["analysis_nodes"]:
        result["analysis_kind"] = "infinite"
    # Earlier builds shipped the auto-evaluation menu with 10M (and a short
    # lived 20M default). Upgrade those defaults to the requested 200M once.
    if data.get("auto_eval_limit_version") != 2 and data.get("auto_eval_nodes") in (10_000_000, 20_000_000):
        result["auto_eval_nodes"] = 200_000_000
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
    result["analysis_limit_version"] = 2
    result["auto_eval_limit_version"] = 2
    return result
