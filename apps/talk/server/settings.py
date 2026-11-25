"""Talk's settings: settings.json (shared) with settings.local.json (this machine, git-ignored) laid over it."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def get() -> dict:
    data = json.loads((ROOT / "server" / "settings.json").read_text())
    local = ROOT / "server" / "settings.local.json"
    if local.exists():
        data.update(json.loads(local.read_text()))
    if os.environ.get("AIHUB_MODELS_DIR"):  # started by AiHub: its SoundModels folder wins
        data["models_dir"] = os.environ["AIHUB_MODELS_DIR"]
    return data


def models_folder() -> Path:
    folder = Path(get()["models_dir"]).expanduser()
    return folder if folder.is_absolute() else ROOT / folder


def hub_url() -> str:
    """AiHub, which Talk asks to think (Code AI's model) and to do things (the other tools)."""
    return os.environ.get("AIHUB_URL") or get()["hub_url"]


def set_local(key: str, value) -> None:
    """Change a setting on this machine only (the voice picked, always listening)."""
    path = ROOT / "server" / "settings.local.json"
    local = json.loads(path.read_text()) if path.exists() else {}
    local[key] = value
    path.write_text(json.dumps(local, indent=2) + "\n")
