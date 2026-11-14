"""Ways of running a video model. A theme names one with its "backend" key.

Every backend has the same shape:

    backend = Backend(device)
    frames = backend.make(request, on_step)  # a list of PIL images, in order
    backend.unload()                         # free the graphics memory

where request is a dict with model / model_config / loras (full paths),
prompt, negative, width, height, frames, fps, steps, guidance, scheduler,
seed, and low_memory (the "Use 3060 settings" switch), and on_step(done,
total) reports progress.

None are written yet: video making comes with the Mac (phase 3). A backend
listed here as None is planned; asking for it raises NotReady, which the
page shows as "not set up yet".
"""

import importlib

MODULES = {
    # Wan 2.2 (and Wan 2.1) through diffusers / PyTorch: cuda, mps or cpu.
    "diffusers-wan": None,
}

NOT_READY_MESSAGE = (
    "Making videos isn't set up yet. Everything else works; the video model "
    "comes when the Mac does."
)

_loaded = {}


class NotReady(Exception):
    """The theme's backend is planned but not written yet."""


def get(name: str, device: str):
    """The backend for a name, made once and kept (so its model stays loaded)."""
    if name not in MODULES:
        raise ValueError(f"Unknown backend '{name}'. Known: {', '.join(MODULES)}")
    if MODULES[name] is None or device == "none":
        raise NotReady(NOT_READY_MESSAGE)
    if name not in _loaded:
        _loaded[name] = importlib.import_module(MODULES[name]).Backend(device)
    return _loaded[name]


def unload_all():
    """Let go of every loaded model (they load again on the next video)."""
    for backend in _loaded.values():
        backend.unload()
