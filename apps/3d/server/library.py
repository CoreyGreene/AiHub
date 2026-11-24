"""The library: every 3D model, each with its versions.

    library/<slug>/model.json         name, created, versions (newest last)
    library/<slug>/pictures/<hash>.<ext>  the 2D pictures they were made from
    library/<slug>/<version>.glb       one file per version

A model's name is what you call it ("Item Fridge"); its slug is the folder
("item-fridge"). Making a model with a name that exists adds versions to it.
"""

import hashlib
import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from . import settings

_lock = threading.Lock()
PICTURE_TYPES = {".png", ".jpg", ".jpeg", ".webp"}


class LibraryError(Exception):
    pass


def root() -> Path:
    path = settings.folder("library_dir")
    path.mkdir(parents=True, exist_ok=True)
    return path


def slug_of(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "model"


def clean_name(name: str) -> str:
    name = " ".join(str(name).split())[:60]
    if not name:
        raise LibraryError("Give the model a name.")
    return name


def _read(slug: str) -> dict | None:
    path = root() / slug / "model.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write(slug: str, data: dict) -> None:
    folder = root() / slug
    folder.mkdir(parents=True, exist_ok=True)
    spare = folder / "model.json.saving"
    spare.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    spare.replace(folder / "model.json")


def _public(slug: str, data: dict) -> dict:
    base = f"files/{slug}"
    versions = [dict(v, url=f"{base}/{v['id']}.glb" if v.get("status") == "done" else None,
                     picture_url=f"{base}/pictures/{v['picture']}") for v in data["versions"]]
    done = [v for v in versions if v.get("status") == "done"]
    cover = data["versions"][0]["picture"] if data["versions"] else ""
    return {"slug": slug, "name": data["name"], "created": data["created"], "versions": versions,
            "count": len(done), "cover": f"{base}/pictures/{cover}" if cover else ""}


def listing() -> list[dict]:
    out = []
    for path in root().iterdir():
        data = _read(path.name) if path.is_dir() else None
        if data:
            out.append(_public(path.name, data))
    return sorted(out, key=lambda m: m["created"], reverse=True)


def get(slug: str) -> dict | None:
    data = _read(slug)
    return _public(slug, data) if data else None


def add_picture(name: str, picture: bytes, suffix: str) -> tuple[str, str]:
    """The model called name (made if new) and the picture stored in it: (slug, picture file)."""
    name = clean_name(name)
    suffix = suffix.lower() if suffix.lower() in PICTURE_TYPES else ".png"
    slug = slug_of(name)
    with _lock:
        data = _read(slug) or {"name": name, "created": time.time(), "versions": []}
        _write(slug, data)
        pictures = root() / slug / "pictures"
        pictures.mkdir(exist_ok=True)
        file = hashlib.sha1(picture).hexdigest()[:12] + suffix
        if not (pictures / file).exists():
            (pictures / file).write_bytes(picture)
    return slug, file


def new_version(slug: str, picture: str, seed: int) -> dict:
    """A version waiting to be made (status "waiting"); its GLB comes later."""
    with _lock:
        data = _read(slug)
        if data is None:
            raise LibraryError("That model isn't there any more.")
        version = {"id": uuid.uuid4().hex[:12], "picture": picture, "seed": seed, "created": time.time(),
                   "status": "waiting"}
        data["versions"].append(version)
        _write(slug, data)
    return version


def update_version(slug: str, version_id: str, **changes) -> None:
    with _lock:
        data = _read(slug)
        if data is None:
            return
        for v in data["versions"]:
            if v["id"] == version_id:
                v.update(changes)
        _write(slug, data)


def paths(slug: str, version_id: str, picture: str) -> tuple[Path, Path]:
    """(the picture file, where the GLB goes)."""
    folder = root() / slug
    return folder / "pictures" / picture, folder / f"{version_id}.glb"


def delete_version(slug: str, version_id: str) -> None:
    with _lock:
        data = _read(slug)
        if data is None:
            raise LibraryError("That model isn't there any more.")
        if any(v["id"] == version_id and v.get("status") in ("waiting", "working") for v in data["versions"]):
            raise LibraryError("That version is still being made. Stop it on the Queue first.")
        data["versions"] = [v for v in data["versions"] if v["id"] != version_id]
        (root() / slug / f"{version_id}.glb").unlink(missing_ok=True)
        if not data["versions"]:
            shutil.rmtree(root() / slug, ignore_errors=True)
            return
        used = {v["picture"] for v in data["versions"]}
        for pic in (root() / slug / "pictures").iterdir():
            if pic.name not in used:
                pic.unlink()
        _write(slug, data)


def delete_model(slug: str) -> None:
    with _lock:
        data = _read(slug)
        if data is None:
            raise LibraryError("That model isn't there any more.")
        if any(v.get("status") in ("waiting", "working") for v in data["versions"]):
            raise LibraryError("Some of its versions are still being made. Stop them on the Queue first.")
        shutil.rmtree(root() / slug)


def rename(slug: str, name: str) -> str:
    """Give a model a new name (and folder). Returns the new slug."""
    name = clean_name(name)
    new = slug_of(name)
    with _lock:
        data = _read(slug)
        if data is None:
            raise LibraryError("That model isn't there any more.")
        if any(v.get("status") in ("waiting", "working") for v in data["versions"]):
            raise LibraryError("Wait until its versions are made.")
        if new != slug and (root() / new).exists():
            raise LibraryError(f"There's already a model called {name}.")
        data["name"] = name
        _write(slug, data)
        if new != slug:
            (root() / slug).rename(root() / new)
    return new


def forget_unfinished() -> None:
    """At start-up: versions left waiting or working by a stop are marked as failed."""
    for path in root().iterdir():
        data = _read(path.name) if path.is_dir() else None
        if not data:
            continue
        changed = False
        for v in data["versions"]:
            if v.get("status") in ("waiting", "working"):
                v.update(status="failed", message="MeshAi was stopped before it was made.")
                changed = True
        if changed:
            _write(path.name, data)
