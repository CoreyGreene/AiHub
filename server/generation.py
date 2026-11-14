"""Where image making plugs in: turns a theme + prompt into a checked picture.

The routes never call a model directly; they go through here. This picks
the theme's backend (server/backends/), builds the prompt from the theme
file, and runs every picture through the nudity check (server/safety.py).
"""

import random

from . import backends, safety, settings


BLOCKED_MESSAGE = "This picture didn't pass the safety check. Try changing the prompt."


class Blocked(Exception):
    """Every try was stopped by the nudity check."""


# Used when a theme file leaves a setting out.
DEFAULTS = {"width": 1024, "height": 1024, "steps": 28, "guidance": 6.0, "scheduler": "euler_a"}


def _setting(theme: dict, key: str):
    return theme.get(key, DEFAULTS[key])


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
        "prompt_before": before.strip(" ,"),
        "prompt_after": after.strip(" ,"),
        "negative": theme.get("negative", ""),
        "safety_negative": settings.get()["safety"]["negative"],
        "backend": theme["backend"],
        "model": {"file": theme["model"], "found": (models / theme["model"]).is_file()},
        "loras": [
            {"file": lora["file"], "weight": lora.get("weight", 1.0), "found": (loras / lora["file"]).is_file()}
            for lora in theme.get("loras", [])
        ],
        "settings": {key: _setting(theme, key) for key in DEFAULTS},
        "use_3060_settings": settings.get()["use_3060_settings"],
    }


def _request(theme: dict, prompt: str, seed: int) -> dict:
    models = settings.folder("models_dir")
    loras = settings.folder("loras_dir")
    negative = ", ".join(n for n in (theme.get("negative"), settings.get()["safety"]["negative"]) if n)
    return {
        "model": models / theme["model"],
        "model_config": models / theme["model_config"],
        "loras": [{"path": loras / lora["file"], "weight": lora.get("weight", 1.0)} for lora in theme.get("loras", [])],
        "prompt": theme["prompt"].replace("{prompt}", prompt),
        "negative": negative,
        **{key: _setting(theme, key) for key in DEFAULTS},
        "seed": seed,
        "low_memory": settings.get()["use_3060_settings"],
        "fp16_vae": models / settings.get()["fp16_vae"],
    }


def generate(theme: dict, prompt: str, on_progress) -> tuple:
    """Make a picture. Returns (image, details). Raises Blocked if every try
    fails the nudity check.

    on_progress(stage, done, total): stage is "loading", "drawing" or "checking".
    """
    backend = backends.get(theme["backend"], settings.device())
    tries = settings.get()["safety"]["tries"]
    for attempt in range(1, tries + 1):
        req = _request(theme, prompt, seed=random.randrange(2**31))
        if not backend.is_loaded(req):
            on_progress("loading", 0, 0)
        image = backend.make(req, lambda done, total: on_progress("drawing", done, total))
        on_progress("checking", 0, 0)
        if safety.is_safe(image):
            details = {
                "seed": req["seed"],
                "model": theme["model"],
                "loras": theme.get("loras", []),
                "steps": req["steps"],
                "size": [req["width"], req["height"]],
                "tries": attempt,
            }
            return image, details
        print(f"Nudity check stopped try {attempt} of {tries}")
    raise Blocked(BLOCKED_MESSAGE)
