"""Ways of running a video model. A theme names one with its "backend" key.

Every backend has the same shape:

    backend = Backend(device)
    frames = backend.make(request, on_step)  # a list of PIL images, in order
    backend.unload()                         # free the graphics memory

where request is a dict with model / model_config / loras (full paths),
prompt, negative, width, height, frames, fps, steps, guidance, scheduler,
seed, and low_memory (the "Use 3060 settings" switch), and on_step(done,
total) reports progress.

A backend listed here as None is planned; asking for it raises NotReady,
which the page shows as "not set up yet". So does any backend while the
video packages (PyTorch) aren't installed.
"""

import importlib

MODULES = {
    # Wan 2.1 (and Wan 2.2 text-to-video) through diffusers / PyTorch: cuda, mps or cpu.
    "diffusers-wan": "server.backends.diffusers_wan",
}

NOT_READY_MESSAGE = (
    "Making videos isn't set up on this computer yet: the video packages "
    "aren't installed (python3 start.py installs them)."
)

_loaded = {}


class NotReady(Exception):
    """The theme's backend is planned but not written yet."""


def get(name: str, device: str, alone: bool = False):
    """The backend for a name, made once and kept (so its model stays loaded).
    alone: let go of the other backends' models first (a 12 GB card holds
    only one at a time)."""
    if name not in MODULES:
        raise ValueError(f"Unknown backend '{name}'. Known: {', '.join(MODULES)}")
    if alone:
        for other, backend in _loaded.items():
            if other != name:
                backend.unload()
    if MODULES[name] is None or device == "none":
        raise NotReady(NOT_READY_MESSAGE)
    if name not in _loaded:
        _loaded[name] = importlib.import_module(MODULES[name]).Backend(device)
    return _loaded[name]


def unload_all():
    """Let go of every loaded model (they load again on the next video)."""
    for backend in _loaded.values():
        backend.unload()
