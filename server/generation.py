"""Where image generation will plug in.

Nothing is connected yet: generate() only says so. A later phase will
load a model here and return the finished image.
"""


def generate(theme: str, prompt: str) -> dict:
    return {
        "status": "not_connected",
        "message": "Image making isn't connected yet. This is just the website for now.",
        "theme": theme,
        "prompt": prompt,
    }
