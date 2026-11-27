"""Where video making plugs in: turns a theme + prompt into a checked video.

The routes never call a model directly; they go through here. This picks
the theme's backend (server/backends/), builds the prompt from the theme
file, and runs every video through the nudity check (server/safety.py).
"""

import random
from pathlib import Path

from . import backends, safety, settings, videos
from .aihub_room import make_room

BLOCKED_MESSAGE = "This video didn't pass the safety check. Try changing the prompt."


class Blocked(Exception):
    """Every try was stopped by the nudity check."""


# Used when a theme file leaves a setting out.
DEFAULTS = {
    "width": 832, "height": 480, "frames": 81, "fps": 16,
    "steps": 30, "guidance": 5.0, "scheduler": "default",
}
MAX_FRAMES = 241


def _setting(theme: dict, key: str):
    return theme.get(key, DEFAULTS[key])


def frames_for_length(theme: dict, seconds: float) -> int:
    fps = _setting(theme, "fps")
    if seconds * fps > MAX_FRAMES:
        raise ValueError(f"At {fps} frames a second, the longest video is about {MAX_FRAMES / fps:.1f} seconds.")
    stride = {"ltx-mlx": 8, "diffusers-wan": 4}.get(theme["backend"], 1)
    return round((seconds * fps - 1) / stride) * stride + 1


def describe(theme: dict) -> dict:
    """Everything a theme does, for the Theme page: the words it adds, the
    model and LoRAs (and whether their files are here), and its settings."""
    models = settings.folder("models_dir")
    loras = settings.folder("loras_dir")
    before, _, after = theme["prompt"].partition("{prompt}")
    return {
        "name": theme["name"],
        "hint": theme.get("hint", ""),
        "notes": theme.get("_notes", ""),
        "prompt": theme["prompt"],
        "prompt_before": before.strip(" ,"),
        "prompt_after": after.strip(" ,"),
        "negative": theme.get("negative", ""),
        "safety_negative": settings.get()["safety"]["negative"],
        "backend": theme["backend"],
        "model": {"file": theme["model"], "found": (models / theme["model"]).exists()},
        "loras": [
            {"file": lora["file"], "weight": lora.get("weight", 1.0), "found": (loras / lora["file"]).is_file()}
            for lora in theme.get("loras", [])
        ],
        "settings": {key: _setting(theme, key) for key in DEFAULTS},
        "use_3060_settings": settings.get()["use_3060_settings"],
    }


# Samplers a theme can pick. "default" is the one the model came with
# (most video models are made for theirs); the backends will know the others.
SCHEDULERS = ("default", "unipc", "flow_euler")
MODEL_TYPES = (".safetensors", ".gguf")


def choices() -> dict:
    """What a theme can choose from when it is changed on the Theme page:
    the model and LoRA files that are here, and the samplers. Video models
    often come as a folder (diffusers format, with model_index.json inside,
    or LTX's MLX layout, with embedded_config.json) rather than one file;
    those are listed too."""
    def files(folder, folders=False):
        if not folder.is_dir():
            return []
        return sorted(
            p.name for p in folder.iterdir()
            if (p.is_file() and p.suffix in MODEL_TYPES) or (folders and any((p / f).is_file() for f in ("model_index.json", "embedded_config.json")))
        )
    return {
        "models": files(settings.folder("models_dir"), folders=True),
        "loras": files(settings.folder("loras_dir")),
        "schedulers": list(SCHEDULERS),
    }


def _request(theme: dict, prompt: str, seed: int, image=None) -> dict:
    models = settings.folder("models_dir")
    loras = settings.folder("loras_dir")
    negative = ", ".join(n for n in (theme.get("negative"), settings.get()["safety"]["negative"]) if n)
    return {
        "model": models / theme["model"],
        "model_config": models / theme["model_config"] if theme.get("model_config") else None,
        "loras": [{"path": loras / lora["file"], "weight": lora.get("weight", 1.0)} for lora in theme.get("loras", [])],
        "prompt": theme["prompt"].replace("{prompt}", prompt),
        "negative": negative,
        **{key: _setting(theme, key) for key in DEFAULTS},
        "seed": seed,
        "image": image,  # a start picture (a file path), for backends that take one
        "low_memory": settings.get()["use_3060_settings"],
    }


def generate(theme: dict, prompt: str, on_progress, image=None) -> tuple:
    """Make a video. Returns (frames, details). Raises Blocked if every try
    fails the nudity check, backends.NotReady while video making isn't set up.
    image: a start picture (file path), for backends that take one (LTX).
    A backend that makes the .mp4 itself (with sound) gives its path, which
    comes back as details["_file"] for videos.keep_new to keep as it is.

    on_progress(stage, done, total): stage is "loading", "drawing" or "checking".
    """
    backend = backends.get(theme["backend"], settings.device(), alone=settings.get()["use_3060_settings"])
    tries = settings.get()["safety"]["tries"]
    for attempt in range(1, tries + 1):
        req = _request(theme, prompt, random.randrange(2**31), image)
        if not backend.is_loaded(req):
            make_room("movie", req["model"])
            on_progress("loading", 0, 0)
        made = backend.make(req, lambda done, total: on_progress("drawing", done, total))
        on_progress("checking", 0, 0)
        file = made if isinstance(made, Path) else None
        frames = videos.read_frames(file) if file else made
        safe, said = safety.check(frames)
        if safe:
            # Enough to make it again (Library → Copy settings), even if
            # the theme changes later.
            details = {
                "seed": req["seed"],
                "model": theme["model"],
                "loras": theme.get("loras", []),
                "words": theme["prompt"],
                "negative": theme.get("negative", ""),
                "steps": req["steps"],
                "guidance": req["guidance"],
                "scheduler": req["scheduler"],
                "size": list(frames[0].size),
                "frames": len(frames),
                "fps": req["fps"],
                "tries": attempt,
                **({"_file": file, "sound": True} if file else {}),
                **({"start_picture": True} if image else {}),
            }
            return frames, details
        if file:
            file.unlink(missing_ok=True)
        print(f"Nudity check stopped try {attempt} of {tries} ({said})", flush=True)
    raise Blocked(BLOCKED_MESSAGE)


def free_memory():
    """Give the graphics memory back when no videos are being made.
    The next video loads the model again."""
    backends.unload_all()
