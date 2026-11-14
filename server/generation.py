"""Where image making plugs in: turns a theme + prompt into a checked picture.

The routes never call a model directly; they go through here. This picks
the theme's backend (server/backends/), builds the prompt from the theme
file, and runs every picture through the nudity check (server/safety.py).
"""

import json
import random
from pathlib import Path

from . import backends, safety, settings

OPTIONS_FILE = Path(__file__).resolve().parent / "options.json"


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
        "prompt": theme["prompt"],
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


# Samplers a theme can pick (the diffusers backend knows these names).
SCHEDULERS = ("euler_a", "euler", "dpm++")
MODEL_TYPES = (".safetensors", ".ckpt")


def choices() -> dict:
    """What a theme can choose from when it is changed on the Theme page:
    the model and LoRA files that are here, and the samplers."""
    def files(folder):
        if not folder.is_dir():
            return []
        return sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix in MODEL_TYPES)
    return {
        "models": files(settings.folder("models_dir")),
        "loras": files(settings.folder("loras_dir")),
        "schedulers": list(SCHEDULERS),
    }


def _options_file() -> dict:
    return json.loads(OPTIONS_FILE.read_text(encoding="utf-8"))


def options() -> dict:
    """The Advanced tab's extra choices, for the page (no prompt words)."""
    data = _options_file()
    return {
        "choices": [
            {"id": c["id"], "label": c["label"], "values": [{"id": v["id"], "label": v["label"]} for v in c["values"]]}
            for c in data["choices"]
        ],
    }


def check_options(chosen: dict) -> dict:
    """Keep only known choices with known values; unknown ones raise ValueError.
    Choices left out get their default (the first value)."""
    data = _options_file()
    out = {}
    for choice in data["choices"]:
        ids = [v["id"] for v in choice["values"]]
        value = chosen.get(choice["id"], ids[0])
        if value not in ids:
            raise ValueError(f"'{value}' isn't one of the {choice['label']} choices.")
        out[choice["id"]] = value
    return out


def _option_words(chosen: dict) -> tuple[str, str]:
    """The words the chosen options add: (prompt, negative)."""
    data = _options_file()
    prompt, negative = [], []
    for choice in data["choices"]:
        for value in choice["values"]:
            if value["id"] == chosen.get(choice["id"]):
                prompt.append(value.get("prompt", ""))
                negative.append(value.get("negative", ""))
    join = lambda parts: ", ".join(p for p in parts if p)
    return join(prompt), join(negative)


def _request(theme: dict, prompt: str, seed: int, chosen: dict) -> dict:
    models = settings.folder("models_dir")
    loras = settings.folder("loras_dir")
    extra, avoid = _option_words(chosen)
    if extra:
        prompt = f"{prompt}, {extra}"
    negative = ", ".join(n for n in (theme.get("negative"), avoid, settings.get()["safety"]["negative"]) if n)
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


def generate(theme: dict, prompt: str, on_progress, chosen: dict | None = None) -> tuple:
    """Make a picture. Returns (image, details). Raises Blocked if every try
    fails the nudity check.

    on_progress(stage, done, total): stage is "loading", "drawing" or "checking".
    chosen: the Advanced tab's options (see check_options).
    """
    chosen = chosen or {}
    backend = backends.get(theme["backend"], settings.device())
    tries = settings.get()["safety"]["tries"]
    for attempt in range(1, tries + 1):
        req = _request(theme, prompt, random.randrange(2**31), chosen)
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
                "size": list(image.size),
                "options": chosen,
                "tries": attempt,
            }
            return image, details
        print(f"Nudity check stopped try {attempt} of {tries}")
    raise Blocked(BLOCKED_MESSAGE)


def free_memory():
    """Give the graphics card's memory back when no pictures are being made.
    The next picture loads the model again (a few seconds)."""
    backends.unload_all()
