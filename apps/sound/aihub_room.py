"""Before loading a model: ask AiHub to make room for it. If it won't fit with some memory still free, Code AI lets
go of language models it's holding but not using (Talk's last). Does nothing when this tool runs on its own."""

import json
import os
import urllib.request
from pathlib import Path


def _size(path) -> int:
    path = Path(path)
    if path.is_file():
        return path.stat().st_size
    total = 0
    for folder, _dirs, files in os.walk(path, followlinks=True):
        for name in files:
            try:
                total += (Path(folder) / name).stat().st_size
            except OSError:
                pass
    return total


def make_room(tool: str, *paths) -> None:
    hub = os.environ.get("AIHUB_URL")
    if not hub:
        return
    body = json.dumps({"tool": tool, "bytes": sum(_size(p) for p in paths if p)}).encode()
    request = urllib.request.Request(hub + "/hub/api/make-room", body, {"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(request, timeout=60).read()
    except OSError:
        pass  # the hub isn't there: load anyway
