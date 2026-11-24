"""Models and LoRAs added from the page (Theme tab). The file comes in as
the request body and is written straight to disk in pieces, so a 7 GB
model never sits in memory. It is checked before it gets its real name.

Only .safetensors files: they hold numbers only. (.ckpt files can carry
code that runs when they are loaded, so they aren't taken from the page.)
"""

import json
import re
import shutil
import struct
from pathlib import Path

from . import settings

FOLDERS = {"model": "models_dir", "lora": "loras_dir"}
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()+-]{0,150}\.safetensors$")
SPARE_SPACE = 2 * 1024**3  # leave this much free on the disk


class Refused(Exception):
    """Shown to the user as it is."""


def target(kind: str, name: str, size: int | None) -> Path:
    """Where the file will go, after checking its name, that it isn't there
    already and that the disk has room for it."""
    if kind not in FOLDERS:
        raise Refused("Unknown kind of file.")
    if not NAME.match(name):
        raise Refused("Only .safetensors files, with a plain file name (letters, numbers, - _ . and spaces).")
    folder = settings.folder(FOLDERS[kind])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if path.exists():
        raise Refused(f"There's already a file called {name}. Pick it from the list instead.")
    if size is not None and shutil.disk_usage(folder).free - size < SPARE_SPACE:
        raise Refused("There isn't enough free disk space for this file.")
    return path


def check(path: Path, kind: str) -> None:
    """A real safetensors file (a small header, then numbers), and for a
    model an SDXL one, the only kind the site can run now."""
    try:
        with path.open("rb") as f:
            length = struct.unpack("<Q", f.read(8))[0]
            if not 2 <= length <= 100 * 1024**2:
                raise ValueError
            header = json.loads(f.read(length))
        if not isinstance(header, dict):
            raise ValueError
    except (OSError, ValueError, struct.error):
        raise Refused("That isn't a working .safetensors file (maybe it didn't finish downloading).")
    if kind == "model" and not any(k.startswith("conditioner.embedders.1.") for k in header):
        raise Refused("That model isn't SDXL (SDXL, Illustrious, Pony or NoobAI). Only SDXL models work here for now.")


async def receive(kind: str, name: str, size: int | None, chunks) -> Path:
    """Write the incoming pieces to a spare file, check it, then give it its
    real name. Nothing is left behind if it fails or is stopped."""
    path = target(kind, name, size)
    spare = path.with_name(f".{name}.uploading")
    try:
        with spare.open("wb") as f:
            async for chunk in chunks:
                f.write(chunk)
        if size is not None and spare.stat().st_size != size:
            raise Refused("The upload stopped part way. Try again.")
        check(spare, kind)
        spare.replace(path)
    finally:
        spare.unlink(missing_ok=True)
    return path
