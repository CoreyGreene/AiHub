"""The nudity check. This website is safe for work: every video goes
through it before anyone sees it, and there is no switch to turn it off.

Two small picture checkers (from the settings) each give a 0..1 "not safe"
score to frames taken from the video (one in every few, and the last). A
frame's score is the two averaged; the video is flagged when enough frames
reach the threshold, or one is very high (check() says how). They
run on the CPU so they don't take graphics memory from the video model.

The checkers need PyTorch and transformers, which come with the video
packages, so they are only loaded when a video is checked.
"""

import os
import threading
from pathlib import Path

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
    from transformers import AutoImageProcessor, AutoModelForImageClassification

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


def sample(frames: list) -> list:
    """The frames that get checked: one in every few, and always the last."""
    every = max(1, int(settings.get()["safety"]["every_frames"]))
    picked = frames[::every]
    if frames and picked[-1] is not frames[-1]:
        picked.append(frames[-1])
    return picked


def scores(frames: list) -> list[list[float]]:
    """Each checker's "not safe" score (0..1) for each checked frame: [checker][frame]."""
    import torch

    rgb = [frame.convert("RGB") for frame in sample(frames)]
    out = []
    with torch.no_grad():
        for model, processor, nsfw in _load():
            out.append([float(x) for x in model(**processor(images=rgb, return_tensors="pt")).logits.softmax(-1)[:, nsfw]])
    return out


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


def check(frames: list) -> tuple[bool, str]:
    """(safe, what the checkers said, for the log). A checked frame's score is the average of the checkers, so
    one checker's flicker can't block a video on its own. Not safe: `frames_needed` or more checked frames at
    `threshold` or above, or any one at `sure` or above. (The checkers flicker frame to frame on harmless
    videos of people, one of them up to 0.5 and more on a single frame; real nudity scores high on both, frame
    after frame.)"""
    s = settings.get()["safety"]
    table = scores(frames)
    per_frame = [sum(col) / len(col) for col in zip(*table)]
    flagged = sum(1 for x in per_frame if x >= s["threshold"])
    worst = max(per_frame)
    safe = flagged < s["frames_needed"] and worst < s["sure"]
    names = [Path(n).name.split("-")[0] for n in s["checkers"]]
    said = (f"worst frame {worst:.2f} (frame {per_frame.index(worst) + 1} of {len(per_frame)}), "
            f"{flagged} at {s['threshold']} or more; " +
            ", ".join(f"{name} up to {max(row):.2f}" for name, row in zip(names, table)))
    return safe, said


def is_safe(frames: list) -> bool:
    return check(frames)[0]
