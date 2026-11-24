"""How much of the Mac's GPU memory is in use, for the line at the top of the page.

    total: how much of the memory macOS lets the GPU use
    used:  memory locked for the GPU by every program (vm_stat's "wired")
    mine:  what the model program takes (its footprint, from top)

Measured in a background thread every few seconds (top takes about a second), so the page never waits for it.
"""

import platform
import re
import subprocess
import threading
import time

from . import models

GB = 1024**3
_latest = {"name": f"Apple GPU ({platform.machine()})"}
_started = False


def _total() -> float:
    try:
        import mlx.core as mx

        info = mx.device_info() if hasattr(mx, "device_info") else mx.metal.device_info()
        return info["max_recommended_working_set_size"] / GB
    except Exception:
        return 0.0


def _wired() -> float:
    out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
    page = int(re.search(r"page size of (\d+)", out).group(1))
    wired = int(re.search(r"Pages wired down:\s+(\d+)", out).group(1))
    return wired * page / GB


def _footprint(pid: int) -> float:
    out = subprocess.run(["top", "-l", "1", "-pid", str(pid), "-stats", "mem"], capture_output=True, text=True).stdout
    match = re.search(r"([\d.]+)([BKMGT])\+?\s*$", out.strip())
    if not match:
        return 0.0
    scale = {"B": 1, "K": 2**10, "M": 2**20, "G": 2**30, "T": 2**40}[match.group(2)]
    return float(match.group(1)) * scale / GB


def _loop():
    total = _total()
    while True:
        try:
            pid = models.loaded()["pid"]
            _latest.update(total_gb=total, used_gb=_wired(), mine_gb=_footprint(pid) if pid else 0.0)
        except Exception:
            pass
        time.sleep(3)


def status() -> dict:
    global _started
    if not _started:
        _started = True
        threading.Thread(target=_loop, daemon=True).start()
    return dict(_latest)
