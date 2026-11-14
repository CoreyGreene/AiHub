"""Where image generation will plug in.

No model yet: generate() waits a moment, then hands back a built-in
demo picture, so the page can show the whole make-a-picture flow. A later
phase will load a model here and return the finished image.
"""

import time
from pathlib import Path

DEMO_IMAGE = Path(__file__).resolve().parent / "assets" / "demo.png"
FAKE_SECONDS = 1


def generate(theme: str, prompt: str) -> Path:
    """Make a picture and return the file it was written to."""
    time.sleep(FAKE_SECONDS)
    return DEMO_IMAGE
