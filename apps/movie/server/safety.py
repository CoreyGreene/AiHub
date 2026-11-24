"""The nudity check. This website is safe for work: every video goes
through it before anyone sees it, and there is no switch to turn it off.

Two small picture checkers (from the settings) each give a 0..1 "not safe"
score to frames taken from the video (one in every few, and the last); the
video is flagged if either checker reaches the threshold on any frame. They
run on the CPU so they don't take graphics memory from the video model.

The checkers need PyTorch and transformers, which come with the video
packages, so they are only loaded when a video is checked.
"""

import threading

from . import settings

_checkers = None
_lock = threading.Lock()


def _load():
    global _checkers
    from transformers import AutoImageProcessor, AutoModelForImageClassification

    with _lock:
        if _checkers is None:
            folder = settings.folder("models_dir")
            _checkers = []
            for name in settings.get()["safety"]["checkers"]:
                path = folder / name
                model = AutoModelForImageClassification.from_pretrained(path, local_files_only=True).eval()
                processor = AutoImageProcessor.from_pretrained(path, local_files_only=True)
                nsfw = [i for i, label in model.config.id2label.items() if label.lower() == "nsfw"][0]
                _checkers.append((model, processor, nsfw))
    return _checkers


def sample(frames: list) -> list:
    """The frames that get checked: one in every few, and always the last."""
    every = max(1, int(settings.get()["safety"]["every_frames"]))
    picked = frames[::every]
    if frames and picked[-1] is not frames[-1]:
        picked.append(frames[-1])
    return picked


def score(frames: list) -> float:
    """0..1: the highest "not safe" score of any checker on any checked frame."""
    import torch

    rgb = [frame.convert("RGB") for frame in sample(frames)]
    worst = 0.0
    with torch.no_grad():
        for model, processor, nsfw in _load():
            probs = model(**processor(images=rgb, return_tensors="pt")).logits.softmax(-1)
            worst = max(worst, float(probs[:, nsfw].max()))
    return worst


def is_safe(frames: list) -> bool:
    return score(frames) < settings.get()["safety"]["threshold"]
