"""The nudity check. This website is safe for work: every picture goes
through it before anyone sees it, and there is no switch to turn it off.

Two small picture checkers (from the settings) each give a 0..1 "not safe"
score; the picture is flagged if either reaches the threshold. They run on
the CPU so they don't take graphics memory from the image model.
"""

import os
import threading
from pathlib import Path

import torch
from transformers import AutoImageProcessor, AutoModelForImageClassification

from . import settings

_checkers = None
_lock = threading.Lock()


def _checker_folder(name: str) -> Path:
    """Started from AiHub, the checkers are in one folder shared by every
    tool (AIHUB_SAFETY_DIR); otherwise in models_dir, as named in the settings."""
    shared = os.environ.get("AIHUB_SAFETY_DIR")
    return Path(shared) / Path(name).name if shared else settings.folder("models_dir") / name


def _load():
    global _checkers
    with _lock:
        if _checkers is None:
            _checkers = []
            for name in settings.get()["safety"]["checkers"]:
                path = _checker_folder(name)
                model = AutoModelForImageClassification.from_pretrained(path, local_files_only=True).eval()
                processor = AutoImageProcessor.from_pretrained(path, local_files_only=True)
                nsfw = [i for i, label in model.config.id2label.items() if label.lower() == "nsfw"][0]
                _checkers.append((model, processor, nsfw))
    return _checkers


def score(image) -> float:
    """0..1: the higher of the checkers' "not safe" scores."""
    rgb = image.convert("RGB")
    worst = 0.0
    with torch.no_grad():
        for model, processor, nsfw in _load():
            probs = model(**processor(images=rgb, return_tensors="pt")).logits.softmax(-1)[0]
            worst = max(worst, float(probs[nsfw]))
    return worst


def is_safe(image) -> bool:
    return score(image) < settings.get()["safety"]["threshold"]
