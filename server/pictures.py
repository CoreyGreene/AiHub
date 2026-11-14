"""Where pictures are kept on disk (outputs/, never in git).

    outputs/new/<id>.png                 just made, not saved yet
    outputs/characters/<folder>/<id>.png saved to a character
    ...each with <id>.json beside it: theme, prompt, character, time.
"""

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

OUTPUTS = Path(__file__).resolve().parent.parent / "outputs"
NEW = OUTPUTS / "new"
CHARACTERS = OUTPUTS / "characters"

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def keep_new(made: Path, theme: str, prompt: str) -> str:
    """Copy a freshly made picture into outputs/new and return its id."""
    NEW.mkdir(parents=True, exist_ok=True)
    pic_id = uuid.uuid4().hex
    shutil.copyfile(made, NEW / f"{pic_id}.png")
    info = {
        "id": pic_id,
        "theme": theme,
        "prompt": prompt,
        "made": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (NEW / f"{pic_id}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return pic_id


def find(pic_id: str) -> Path | None:
    """The picture file for an id, wherever it is kept."""
    if not ID_PATTERN.match(pic_id):
        return None
    for path in [NEW / f"{pic_id}.png", *CHARACTERS.glob(f"*/{pic_id}.png")]:
        if path.is_file():
            return path
    return None


def folder_name(character: str) -> str:
    """A safe folder name for a character: 'Grim the Goblin' -> 'grim-the-goblin'."""
    return re.sub(r"[^a-z0-9]+", "-", character.lower()).strip("-")


def save_to_character(pic_id: str, character: str) -> None:
    """Move a picture (and its settings) into the character's folder."""
    picture = find(pic_id)
    if picture is None:
        raise FileNotFoundError(pic_id)
    folder = CHARACTERS / folder_name(character)
    folder.mkdir(parents=True, exist_ok=True)

    info_path = picture.with_suffix(".json")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    info["character"] = character
    (folder / f"{pic_id}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    if info_path.parent != folder:
        info_path.unlink()
    if picture.parent != folder:
        shutil.move(picture, folder / picture.name)
