"""Themes are JSON files in the themes folder (server/theme/ by default).

Each file is one theme; its id is the file name without .json. Adding a
theme needs no code change and no restart: the folder is read each time.
See server/theme/README.md for the keys. (Files in subfolders, like
examples/, are not themes.)
"""

import json

from . import settings

REQUIRED = ("name", "backend", "model", "prompt")


def load() -> dict[str, dict]:
    themes = {}
    for path in sorted(settings.folder("themes_dir").glob("*.json")):
        try:
            theme = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            print(f"Skipping theme {path.name}: {err}")
            continue
        missing = [key for key in REQUIRED if key not in theme]
        if missing:
            print(f"Skipping theme {path.name}: missing {', '.join(missing)}")
            continue
        themes[path.stem] = theme
    return themes


def public_list() -> list[dict]:
    """What the page needs for the theme picker."""
    return [{"id": tid, "name": t["name"], "hint": t.get("hint", "")} for tid, t in load().items()]


def get(theme_id: str) -> dict | None:
    return load().get(theme_id)
