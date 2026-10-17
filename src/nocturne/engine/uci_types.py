"""External UCI data only: no move search or evaluation implementation."""

from dataclasses import dataclass, field
import re


@dataclass
class UciOption:
    name: str
    kind: str
    default: str = ""
    minimum: int = 0
    maximum: int = 0
    choices: list[str] = field(default_factory=list)

    def validate(self, value):
        text = str(value)
        if any(c in text for c in "\r\n\0"):
            raise ValueError("Engine option cannot contain control characters")
        if self.kind == "spin":
            number = int(text)
            if not self.minimum <= number <= self.maximum:
                raise ValueError(f"{self.name}: choose {self.minimum}–{self.maximum}")
            return str(number)
        if self.kind == "check":
            if isinstance(value, bool):
                return str(value).lower()
            if text.lower() not in ("true", "false"):
                raise ValueError(f"{self.name}: expected true/false")
            return text.lower()
        if self.kind == "combo" and text not in self.choices:
            raise ValueError(f"{self.name}: unsupported choice")
        if self.kind == "button":
            return ""
        return text


def parse_option(line):
    match = re.fullmatch(r"option name (.+?) type (check|spin|combo|button|string)(?: (.*))?", line)
    if not match:
        return None
    name, kind, rest = match.groups()
    if kind == "string":
        return UciOption(name, kind, (rest or "")[8:] if (rest or "").startswith("default ") else "")
    values = {}
    choices = []
    for key, value in re.findall(
        r"(default|min|max|var)\s+(.*?)(?=\s+(?:default|min|max|var)\s+|$)", rest or ""
    ):
        if key == "var":
            choices.append(value)
        else:
            values[key] = value
    try:
        return UciOption(
            name,
            kind,
            values.get("default", ""),
            int(values.get("min", 0)),
            int(values.get("max", 0)),
            choices,
        )
    except ValueError:
        return None


def parse_info(line):
    """Preserve score type/bounds; WDL exists only when explicitly reported."""
    if not line.startswith("info ") or line.startswith("info string "):
        return None
    tokens = line.split()[1:]
    result = {"multipv": 1, "pv": []}
    i = 0
    try:
        while i < len(tokens):
            key = tokens[i]
            if key == "pv":
                result["pv"] = tokens[i + 1 :]
                break
            if key == "score" and i + 2 < len(tokens):
                kind, value = tokens[i + 1 : i + 3]
                if kind not in ("cp", "mate"):
                    return None
                result.update(score_type=kind, score_value=int(value), bound="exact")
                i += 3
                if i < len(tokens) and tokens[i] in ("lowerbound", "upperbound"):
                    result["bound"] = tokens[i]
                    i += 1
                continue
            if key == "wdl":
                wdl = tuple(int(v) for v in tokens[i + 1 : i + 4])
                if len(wdl) == 3 and min(wdl) >= 0 and sum(wdl) == 1000:
                    result["wdl"] = wdl
                i += 4
                continue
            if key in ("depth", "seldepth", "nodes", "nps", "time", "hashfull", "tbhits", "multipv"):
                result[key] = max(0, int(tokens[i + 1]))
                i += 2
            else:
                i += 1
    except (ValueError, IndexError):
        return None
    if "score_type" not in result or not result["pv"]:
        return None
    value = result["score_value"]
    # Numeric plotting coordinate is separate from the actual mate score.
    result["score"] = (
        value if result["score_type"] == "cp" else (30000 - min(abs(value), 999)) * (1 if value >= 0 else -1)
    )
    result["seconds"] = result.get("time", 0) / 1000
    for key in ("depth", "seldepth", "nodes", "nps", "hashfull", "tbhits"):
        result.setdefault(key, 0)
    return result


def score_label(info, perspective=1):
    value = info["score_value"] * perspective
    text = f"#{value}" if info["score_type"] == "mate" else f"{value / 100:+.2f}"
    bound = info.get("bound", "exact")
    if perspective < 0:
        bound = {"lowerbound": "upperbound", "upperbound": "lowerbound"}.get(bound, bound)
    return {"lowerbound": "≥ ", "upperbound": "≤ "}.get(bound, "") + text


@dataclass(frozen=True)
class AnalysisLimits:
    depth: int = 24
    seconds: float = 3.0
    nodes: int | None = None

    def __post_init__(self):
        import math

        if not 1 <= self.depth <= 128 or not math.isfinite(self.seconds) or self.seconds <= 0:
            raise ValueError("Invalid external engine search limits")
        if self.nodes is not None and self.nodes < 1:
            raise ValueError("Node limit must be positive")


def plot_score_label(score):
    if abs(score) >= 29000:
        return ("#" if score >= 0 else "#-") + str(max(0, 30000 - abs(score)))
    return f"{score / 100:+.2f}"
