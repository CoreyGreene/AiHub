"""What the graphics card is and how much of its memory is in use.

    used:      memory in use on the whole card (every program)
    allocated: memory this website has taken (the model, mostly)
    total:     the card's memory

On a Mac the GPU shares the computer's memory, so "total" is how much of it
Apple lets the GPU use, and "used" is what PyTorch has taken.
"""

import platform

import torch

from . import settings

GB = 1024**3


def status() -> dict:
    device = settings.device()
    if device == "cuda":
        free, total = torch.cuda.mem_get_info()
        return {
            "device": "cuda",
            "name": torch.cuda.get_device_name(),
            "total_gb": total / GB,
            "used_gb": (total - free) / GB,
            "allocated_gb": torch.cuda.memory_reserved() / GB,
        }
    if device == "mps":
        allocated = torch.mps.driver_allocated_memory()
        return {
            "device": "mps",
            "name": f"Apple GPU ({platform.machine()})",
            "total_gb": torch.mps.recommended_max_memory() / GB,
            "used_gb": allocated / GB,
            "allocated_gb": allocated / GB,
        }
    return {"device": "cpu", "name": "No graphics card (using the processor)"}
