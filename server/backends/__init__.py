"""Ways of running a model. A theme names one with its "backend" key.

Every backend has the same shape:

    backend = Backend(device)
    image = backend.make(request, on_step)   # a PIL image
    backend.unload()                         # free the graphics card's memory

where request is a dict with model / model_config / loras (full paths),
prompt, negative, width, height, steps, guidance, scheduler, seed, and
low_memory (the "Use 3060 settings" switch) with fp16_vae, and
on_step(done, total) reports progress. Later: MLX and Core ML backends for
the Mac, with the same shape.
"""

import importlib

MODULES = {
    "diffusers-sdxl": "server.backends.diffusers_sdxl",
}

_loaded = {}


def get(name: str, device: str):
    """The backend for a name, made once and kept (so its model stays loaded)."""
    if name not in MODULES:
        raise ValueError(f"Unknown backend '{name}'. Known: {', '.join(MODULES)}")
    if name not in _loaded:
        _loaded[name] = importlib.import_module(MODULES[name]).Backend(device)
    return _loaded[name]


def unload_all():
    """Let go of every loaded model (they load again on the next picture)."""
    for backend in _loaded.values():
        backend.unload()
