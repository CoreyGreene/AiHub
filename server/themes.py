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


def save(theme_id: str, changes: dict) -> None:
    """Write the changed keys into an existing theme file. Keys the page
    doesn't edit (backend, model_config, notes, anything else) are kept."""
    if theme_id not in load():
        raise KeyError(theme_id)
    path = settings.folder("themes_dir") / f"{theme_id}.json"
    theme = json.loads(path.read_text(encoding="utf-8"))
    theme.update(changes)
    if not theme.get("hint"):
        theme.pop("hint", None)
    # Write to a spare file first, so a crash can't leave half a theme.
    spare = path.with_suffix(".json.saving")
    spare.write_text(json.dumps(theme, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    spare.replace(path)
