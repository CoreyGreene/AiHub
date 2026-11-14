"""Where pictures are kept on disk (the outputs folder, never in git).

    outputs/new/<id>.png                 just made, not saved yet
    outputs/characters/<folder>/<id>.png saved to a character
    ...each with <id>.json beside it: theme, prompt, seed, character, time.
"""

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import settings

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _new() -> Path:
    return settings.folder("outputs_dir") / "new"


def _characters() -> Path:
    return settings.folder("outputs_dir") / "characters"


def keep_new(image, info: dict) -> str:
    """Save a freshly made picture into outputs/new and return its id."""
    folder = _new()
    folder.mkdir(parents=True, exist_ok=True)
    pic_id = uuid.uuid4().hex
    image.save(folder / f"{pic_id}.png")
    info = {"id": pic_id, **info, "made": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (folder / f"{pic_id}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return pic_id


def find(pic_id: str) -> Path | None:
    """The picture file for an id, wherever it is kept."""
    if not ID_PATTERN.match(pic_id):
        return None
    for path in [_new() / f"{pic_id}.png", *_characters().glob(f"*/{pic_id}.png")]:
        if path.is_file():
            return path
    return None


def is_saved(path: Path) -> bool:
    return path.parent.parent == _characters()


def folder_name(character: str) -> str:
    """A safe folder name for a character: 'Grim the Goblin' -> 'grim-the-goblin'."""
    return re.sub(r"[^a-z0-9]+", "-", character.lower()).strip("-")


def save_to_character(pic_id: str, character: str) -> None:
    """Move a picture (and its settings) into the character's folder."""
    picture = find(pic_id)
    if picture is None:
        raise FileNotFoundError(pic_id)
    folder = _characters() / folder_name(character)
    folder.mkdir(parents=True, exist_ok=True)

    info_path = picture.with_suffix(".json")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    info["character"] = character
    (folder / f"{pic_id}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    if info_path.parent != folder:
        info_path.unlink()
    if picture.parent != folder:
        shutil.move(picture, folder / picture.name)


def list_characters() -> list[dict]:
    """Every character, with its first picture as the cover."""
    out = []
    root = _characters()
    if not root.is_dir():
        return out
    for folder in root.iterdir():
        infos = []
        for path in folder.glob("*.json"):
            try:
                infos.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        infos = [i for i in infos if (folder / f"{i.get('id')}.png").is_file()]
        if not infos:
            continue
        infos.sort(key=lambda i: i.get("made", ""))
        first = infos[0]
        out.append({
            "name": first.get("character", folder.name),
            "folder": folder.name,
            "count": len(infos),
            "cover": f"api/pictures/{first['id']}",
        })
    out.sort(key=lambda c: c["name"].lower())
    return out
