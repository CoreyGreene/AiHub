"""Where image making plugs in: turns a theme + prompt into a checked picture.

The routes never call a model directly; they go through here. This picks
the theme's backend (server/backends/), builds the prompt from the theme
file, and runs every picture through the nudity check (server/safety.py).
"""

import random

from . import backends, pictures, safety, settings

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
SCHEDULERS = ("euler_a", "euler", "dpm++", "dpm++_karras")
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
    backend = backends.get(theme["backend"], settings.device(), alone=settings.get()["use_3060_settings"])
    tries = settings.get()["safety"]["tries"]
    for attempt in range(1, tries + 1):
        req = _request(theme, prompt, random.randrange(2**31))
        if not backend.is_loaded(req):
            on_progress("loading", 0, 0)
        image = backend.make(req, lambda done, total: on_progress("drawing", done, total))
        on_progress("checking", 0, 0)
        if safety.is_safe(image):
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
                "size": list(image.size),
                "tries": attempt,
            }
            return image, details
        print(f"Nudity check stopped try {attempt} of {tries}")
    raise Blocked(BLOCKED_MESSAGE)


def edit(pic_id: str, instruction: str, on_progress) -> tuple:
    """Change a picture by an instruction ("make his cloak red") with the
    edit model (settings.json "edit"). Returns (image, details) like
    generate(); details are the first picture's, so Copy settings still
    makes the original, plus "edits": every change made, in order."""
    from PIL import Image

    path = pictures.find(pic_id)
    source = pictures.info(pic_id)
    if path is None or source is None:
        raise FileNotFoundError("That picture isn't here any more.")
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    cfg = settings.get()["edit"]
    # Squeeze it in (4-bit reader, the parts taking turns, nothing else
    # loaded) unless this machine has room for it all at once.
    low = settings.memory_gb() < cfg["roomy_gb"]
    backend = backends.get(cfg["backend"], settings.device(), alone=low)
    tries = settings.get()["safety"]["tries"]
    for attempt in range(1, tries + 1):
        req = {
            "folder": settings.folder("models_dir") / cfg["folder"],
            "gguf": cfg["gguf"],
            "lightning": cfg.get("lightning", ""),
            "image": image,
            "prompt": instruction,
            # Same size as the picture, in steps of 16 (what the model needs).
            "width": image.width // 16 * 16,
            "height": image.height // 16 * 16,
            "steps": cfg["steps"],
            "guidance": cfg["guidance"],
            "seed": random.randrange(2**31),
            "low_memory": low,
        }
        on_progress("loading", 0, 0)  # when squeezed, the parts load in turns each time
        result = backend.make(req, lambda done, total: on_progress("drawing", done, total))
        on_progress("checking", 0, 0)
        if safety.is_safe(result):
            keep = {k: v for k, v in source.items() if k not in ("id", "made", "character", "tries")}
            change = {"prompt": instruction, "from": pic_id, "seed": req["seed"], "model": cfg["folder"]}
            return result, {**keep, "edits": [*source.get("edits", []), change], "tries": attempt}
        print(f"Nudity check stopped edit try {attempt} of {tries}")
    raise Blocked(BLOCKED_MESSAGE)


def free_memory():
    """Give the graphics card's memory back when no pictures are being made.
    The next picture loads the model again (a few seconds)."""
    backends.unload_all()
