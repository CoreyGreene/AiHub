"""Settings from hub/settings.json, with hub/settings.local.json on top."""

import json
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "hub" / "settings.json"
LOCAL = ROOT / "hub" / "settings.local.json"


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
    """A folder from the settings: relative to the project, or a full path (~ allowed)."""
    return (ROOT / Path(get()[key]).expanduser()).resolve()


def set_local(key: str, value) -> None:
    """Change a setting on this machine only (hub/settings.local.json)."""
    local = json.loads(LOCAL.read_text(encoding="utf-8")) if LOCAL.exists() else {}
    local[key] = value
    LOCAL.write_text(json.dumps(local, indent=2) + "\n", encoding="utf-8")
    get.cache_clear()
