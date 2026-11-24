"""The Saved list: bulk files (and pipelines) kept in CodeAi, to start again or chain into a pipeline.

saved/<name>.json is a bulk file, exactly as you'd open it on the Bulk tab; saved/pipelines/<name>.json is a pipeline:
{"name": ..., "steps": ["<a saved bulk file's name>", ...]}. Both folders are git-ignored (they're yours, not CodeAi's).
"""

import json
import re
import time
from pathlib import Path

from . import settings


class SavedError(Exception):
    pass


def slug(name: str) -> str:
    """A file name from a title: "Make these fit!" -> "make-these-fit"."""
    out = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:60]
    if not out:
        raise SavedError("Give it a name first.")
    return out


def _dir(kind: str) -> Path:
    base = settings.folder("saved_dir")
    if kind == "pipeline":
        base = base / "pipelines"
        base.mkdir(exist_ok=True)
    return base


def _path(kind: str, name: str) -> Path:
    return _dir(kind) / f"{slug(name)}.json"


def listing(kind: str = "bulk") -> list[dict]:
    out = []
    for p in sorted(_dir(kind).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        entry = {"id": p.stem, "name": data.get("name") or p.stem, "saved": p.stat().st_mtime}
        if kind == "bulk":
            entry["items"] = len(data.get("items") or []) if isinstance(data.get("items"), list) else 0
        else:
            entry["steps"] = data.get("steps") or []
        out.append(entry)
    return out


def get(kind: str, name: str) -> dict:
    p = _path(kind, name)
    if not p.is_file():
        raise SavedError(f"There's no saved {kind} called {name}.")
    return {"id": p.stem, "text": p.read_text(encoding="utf-8")}


def save(kind: str, name: str, text: str, check=None) -> dict:
    """Save it under name (an old one with that name is replaced). check(data) raises if it isn't a good one."""
    try:
        data = json.loads(text)
    except ValueError as err:
        raise SavedError(f"That isn't valid JSON ({err}).")
    if check:
        check(data)
    p = _path(kind, name)
    replaced = p.exists()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    tmp.replace(p)
    return {"id": p.stem, "replaced": replaced, "saved": time.time()}


def delete(kind: str, name: str) -> bool:
    p = _path(kind, name)
    if not p.exists():
        return False
    p.unlink()
    return True
