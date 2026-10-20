"""Persist F12's frozen work list, never a running process or UCI generation."""


def checkpoint(state):
    if not state or state.get("kind") != "auto_eval":
        return None
    return {key: state[key] for key in (
        "kind", "game_id", "line", "index", "seconds", "depth", "nodes", "multipv", "job_profile", "job_options"
    ) if key in state} | {"version": 1}


def restore(game):
    saved = game.metadata.get("auto_eval_job")
    if (not isinstance(saved, dict) or saved.get("version") != 1 or saved.get("game_id") != game.id
            or saved.get("kind") != "auto_eval" or "nodes" not in saved):
        return None
    line, index = saved.get("line"), saved.get("index")
    if (not isinstance(line, list) or not line or line[0] != 0
            or any(type(i) is not int or not 0 <= i < len(game.nodes) for i in line)
            or any(game.nodes[child].parent != parent for parent, child in zip(line, line[1:]))
            or type(index) is not int or not 0 <= index < len(line)
            or type(saved.get("multipv")) is not int or not 1 <= saved["multipv"] <= 32
            or (saved.get("nodes") is not None and (type(saved["nodes"]) is not int or saved["nodes"] < 1))
            or not isinstance(saved.get("job_profile"), str)
            or not isinstance(saved.get("job_options"), dict)):
        return None
    return {
        "kind": "auto_eval", "game_id": game.id, "line": line.copy(), "index": index,
        "seconds": 600, "depth": 128, "nodes": saved["nodes"], "multipv": min(5, saved["multipv"]),
        "job_profile": saved["job_profile"], "job_options": dict(saved["job_options"]),
        "paused": True, "stage": "best", "generation": None, "info": None,
        "message": "Saved auto-evaluation · press F12 to resume at the unfinished position",
    }
