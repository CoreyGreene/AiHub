"""The tools in apps/: start one when its tile is opened, stop it, and say what's running.

Each tool runs as its own program (its own start.py and .venv, since their Python
packages clash), on its own port on this computer only. Memory is the tool and
everything it started (a model server, the TRELLIS worker), the same number
Activity Monitor shows as "Memory".
"""

import ctypes
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import settings

_lock = threading.Lock()
_procs: dict[str, subprocess.Popen] = {}
_state: dict[str, str] = {}  # starting / failed (running and stopped are looked up)
_errors: dict[str, str] = {}


def apps() -> list[dict]:
    return settings.get()["apps"]


def find(app_id: str) -> dict | None:
    return next((a for a in apps() if a["id"] == app_id), None)


def folder(app: dict) -> Path:
    return (settings.ROOT / app["folder"]).resolve()


def log_path(app: dict) -> Path:
    logs = settings.ROOT / "logs"
    logs.mkdir(exist_ok=True)
    return logs / f"{app['id']}.log"


def set_up(app: dict) -> bool:
    """A tool is set up once its .venv exists. The hub never makes one itself:
    some install several GB (PyTorch), so that's done by hand, once."""
    return (folder(app) / ".venv").exists()


def answering(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def state(app: dict) -> str:
    """running / starting / stopped / failed / not_set_up"""
    with _lock:
        s = _state.get(app["id"])
    if s == "starting":
        return s
    if answering(app["port"]):
        return "running"
    if not set_up(app):
        return "not_set_up"
    return s or "stopped"


def start(app: dict) -> None:
    """Start the tool if it isn't running yet; returns at once (it starts in the background)."""
    if state(app) in ("running", "starting") or not set_up(app):
        return
    models = settings.folder("models_dir") / app["models"]
    env = {
        **os.environ,
        "AIHUB": "1",
        "AIHUB_MODELS_DIR": str(models),
        "AIHUB_SAFETY_DIR": str(settings.folder("models_dir") / settings.get()["safety_models"]),
    }
    log = open(log_path(app), "a")
    log.write(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} starting {app['name']}\n")
    log.flush()
    proc = subprocess.Popen(
        [sys.executable, "start.py", "--host", "127.0.0.1", "--port", str(app["port"])],
        cwd=folder(app), env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        start_new_session=True,  # its own process group, so Stop ends everything it started
    )
    with _lock:
        _procs[app["id"]] = proc
        _state[app["id"]] = "starting"
        _errors.pop(app["id"], None)
    threading.Thread(target=_wait_until_up, args=(app, proc), daemon=True).start()


def _wait_until_up(app: dict, proc: subprocess.Popen) -> None:
    deadline = time.time() + settings.get()["start_seconds"]
    while time.time() < deadline:
        if answering(app["port"]):
            with _lock:
                _state.pop(app["id"], None)
            return
        if proc.poll() is not None:
            break
        time.sleep(0.4)
    _end(proc)
    with _lock:
        _state[app["id"]] = "failed"
        _errors[app["id"]] = _last_lines(log_path(app)) or "It didn't start."


def _last_lines(path: Path, n: int = 12) -> str:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:]).strip()


def stop(app: dict) -> None:
    with _lock:
        proc = _procs.pop(app["id"], None)
        _state.pop(app["id"], None)
    if proc and proc.poll() is None:
        _end(proc)
    else:
        # Started some other way (or by an earlier hub): end whatever answers on its port.
        for pid in _tree(_listener(app["port"])):
            _signal(pid, signal.SIGTERM)


def _end(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def stop_all() -> None:
    for app in apps():
        with _lock:
            proc = _procs.get(app["id"])
        if proc and proc.poll() is None:
            stop(app)


def _signal(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


# ---- memory -------------------------------------------------------------------

def _children() -> dict[int, list[int]]:
    out = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True).stdout
    kids: dict[int, list[int]] = {}
    for line in out.splitlines():
        pid, ppid = (int(x) for x in line.split())
        kids.setdefault(ppid, []).append(pid)
    return kids


def _tree(root: int | None) -> list[int]:
    if not root:
        return []
    kids, todo, seen = _children(), [root], []
    while todo:
        pid = todo.pop()
        seen.append(pid)
        todo.extend(kids.get(pid, []))
    return seen


def _listener(port: int) -> int | None:
    out = subprocess.run(["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
                         capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


class _RUsage(ctypes.Structure):  # rusage_info_v2 (macOS)
    _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in (
        "user_time", "system_time", "pkg_idle_wkups", "interrupt_wkups", "pageins", "wired_size",
        "resident_size", "phys_footprint", "proc_start_abstime", "proc_exit_abstime",
        "child_user_time", "child_system_time", "child_pkg_idle_wkups", "child_interrupt_wkups",
        "child_pageins", "child_elapsed_abstime", "diskio_bytesread", "diskio_byteswritten")]


_libc = ctypes.CDLL("libc.dylib") if sys.platform == "darwin" else None


def _footprint(pid: int) -> int:
    """Memory one program uses: its footprint on a Mac (counts graphics memory too), else its RSS."""
    if _libc:
        info = _RUsage()
        if _libc.proc_pid_rusage(pid, 2, ctypes.byref(info)) == 0:
            return info.phys_footprint
        return 0
    try:
        return int(Path(f"/proc/{pid}/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return 0


def memory(app: dict) -> int:
    with _lock:
        proc = _procs.get(app["id"])
    root = proc.pid if proc and proc.poll() is None else _listener(app["port"])
    return sum(_footprint(pid) for pid in _tree(root))


def mac_memory() -> dict:
    """{used, total} in bytes for the whole computer (used = apps + wired + compressed, like Activity Monitor)."""
    if sys.platform != "darwin":
        info = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        kb = lambda k: int(info[k].split()[0]) * 1024  # noqa: E731
        return {"used": kb("MemTotal") - kb("MemAvailable"), "total": kb("MemTotal")}
    total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
    vm = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout.splitlines()
    page = int(vm[0].split("page size of")[1].split()[0])
    pages = {k.strip(): int(v.strip().rstrip(".")) for k, v in (l.split(":") for l in vm[1:] if ":" in l)}
    app_pages = pages.get("Anonymous pages", 0) - pages.get("Pages purgeable", 0)
    used = (app_pages + pages.get("Pages wired down", 0) + pages.get("Pages occupied by compressor", 0)) * page
    return {"used": used, "total": total}


def status() -> dict:
    out = []
    for app in apps():
        s = state(app)
        out.append({
            "id": app["id"], "name": app["name"], "about": app.get("about", ""), "state": s,
            "memory": memory(app) if s == "running" else 0,
            "error": _errors.get(app["id"], "") if s == "failed" else "",
        })
    return {"apps": out, "mac": mac_memory()}
