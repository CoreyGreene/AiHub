"""Where image making plugs in: turns a theme + prompt into a checked picture.

The routes never call a model directly; they go through here. This picks
the theme's backend (server/backends/), builds the prompt from the theme
file, and runs every picture through the nudity check (server/safety.py).
"""

import random

from . import backends, safety, settings


class Blocked(Exception):
    """Every try was stopped by the nudity check."""


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
        "width": theme.get("width", 1024),
        "height": theme.get("height", 1024),
        "steps": theme.get("steps", 28),
        "guidance": theme.get("guidance", 6.0),
        "scheduler": theme.get("scheduler", "euler_a"),
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
    raise Blocked("This picture didn't pass the safety check. Try changing the prompt.")
