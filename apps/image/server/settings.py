"""Settings from server/settings.json, with server/settings.local.json on top.

Nothing about models, folders or safety is written in the code: it all
comes from these files and the theme files.
"""

import json
import os
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "server" / "settings.json"
LOCAL = ROOT / "server" / "settings.local.json"


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
    # Started from AiHub: it says where this tool's models are (one setting for every tool).
    if os.environ.get("AIHUB_MODELS_DIR"):
        data["models_dir"] = os.environ["AIHUB_MODELS_DIR"]
    return data


def set_local(key: str, value) -> None:
    """Change a setting on this machine only (saved in settings.local.json)."""
    local = json.loads(LOCAL.read_text(encoding="utf-8")) if LOCAL.exists() else {}
    local[key] = value
    LOCAL.write_text(json.dumps(local, indent=2) + "\n", encoding="utf-8")
    get.cache_clear()


def folder(key: str) -> Path:
    """A folder from the settings, e.g. folder("models_dir")."""
    return (ROOT / get()[key]).resolve()


@cache
def memory_gb() -> float:
    """How much memory the models can use, in GB: the card's own memory on
    NVIDIA, or the whole machine's on a Mac (shared by CPU and GPU) and on
    the CPU. Measured, so a big machine needs no setting. 0 if unknown."""
    import os

    import torch

    if device() == "cuda":
        return torch.cuda.get_device_properties(0).total_memory / 2**30
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except (ValueError, OSError, AttributeError):  # e.g. Windows
        return 0.0


def device() -> str:
    """cuda (NVIDIA), then mps (Apple), then cpu, unless the settings name one."""
    wanted = get().get("device", "auto")
    if wanted != "auto":
        return wanted
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"
