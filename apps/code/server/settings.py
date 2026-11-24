"""Settings from server/settings.json, with server/settings.local.json on top."""

import json
import os
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "server" / "settings.json"
LOCAL = ROOT / "server" / "settings.local.json"


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key, value in extra.items():
        out[key] = _merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


@cache
def get() -> dict:
    data = json.loads(SHARED.read_text(encoding="utf-8"))
    if LOCAL.exists():
        data = _merge(data, json.loads(LOCAL.read_text(encoding="utf-8")))
    return data


def folder(key: str) -> Path:
    """A folder from the settings, e.g. folder("history_dir"), made if missing."""
    path = (ROOT / get()[key]).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def models() -> list[dict]:
    """The models you can pick: only those whose folder is on this computer.
    A path that's just a folder name is looked for in the models folder AiHub
    gives (AIHUB_MODELS_DIR), else in models_dir."""
    out = []
    base = Path(os.environ.get("AIHUB_MODELS_DIR") or get().get("models_dir", "models")).expanduser()
    for m in get()["models"]:
        path = Path(m["path"]).expanduser()
        if not path.is_absolute():
            path = (ROOT / base / path).resolve()
        if (path / "config.json").exists():
            out.append({**m, "path": str(path)})
    return out


def model(model_id: str) -> dict | None:
    return next((m for m in models() if m["id"] == model_id), None)


def thinking(m: dict) -> list[dict]:
    """The Thinking choices this model has ([] = none): [{id, label, where}], where = "standard", "advanced" or
    "both" (which Ask tab shows it). The first one a tab shows is its default there."""
    levels = get()["thinking_levels"]
    return [{"id": t, "label": levels[t]["label"], "where": levels[t].get("where", "both")}
            for t in m.get("thinking", []) if t in levels]


def budget(m: dict, level: str) -> int:
    """The most thinking tokens this level allows (0 = no limit)."""
    if level not in [t["id"] for t in thinking(m)]:
        return 0
    return int(get()["thinking_levels"][level].get("budget", 0))


def template(m: dict, level: str) -> dict:
    """What the model's chat template is given for this thinking level (its default if the level isn't one of its)."""
    choices = [t["id"] for t in thinking(m)]
    if not choices:
        return {}
    return dict(get()["thinking_levels"][level if level in choices else choices[0]]["template"])
