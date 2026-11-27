"""TRELLIS.2, run in its own Python (it needs packages that clash with ours).

server/trellis_worker.py is started with trellis-mac's .venv python and kept
running, so the model (about 18 GB, a minute to load) loads once and every job
after that goes straight to work. After settings "idle_minutes" with no job it
is stopped to give the memory back. One job at a time (jobs.py makes sure).
"""

import json
import os
import subprocess
import threading
import time
from pathlib import Path

from . import settings
from .aihub_room import make_room

MARK = "@@MESHAI "
WORKER = Path(__file__).with_name("trellis_worker.py")


class TrellisError(Exception):
    pass


class _Stopped(Exception):
    pass


_proc: subprocess.Popen | None = None
_lock = threading.Lock()  # one job at a time
_last_used = 0.0
_idle_watch = None


def _paths() -> tuple[Path, Path]:
    folder = settings.folder("trellis_dir")
    return folder, folder / ".venv" / "bin" / "python"


def problem() -> str:
    """Why TRELLIS can't run here, or "" if it can."""
    folder, python = _paths()
    if not folder.is_dir():
        return f"TRELLIS isn't at {folder} (settings: trellis_dir)."
    if not python.exists():
        return f"TRELLIS isn't set up: no {python}. Run its setup.sh first."
    if not (folder / "local-model" / "pipeline.json").exists():
        return "TRELLIS has no local-model/pipeline.json (see trellis-mac/CLAUDE.md)."
    return ""


def loaded() -> bool:
    return _proc is not None and _proc.poll() is None


def log_path() -> Path:
    path = settings.folder("logs_dir")
    path.mkdir(parents=True, exist_ok=True)
    return path / "trellis.log"


def _model_paths(folder: Path) -> list[Path]:
    """What the worker loads: local-model/ and the folders its pipeline.json names (for AiHub's make-room)."""
    found = [folder / "local-model"]

    def walk(value):
        if isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif isinstance(value, str) and value.startswith("/") and Path(value).exists():
            found.append(Path(value))

    try:
        walk(json.loads((folder / "local-model" / "pipeline.json").read_text()))
    except (OSError, ValueError):
        pass
    return found


def _start() -> None:
    global _proc, _idle_watch
    folder, python = _paths()
    make_room("3d", *_model_paths(folder))
    env = dict(os.environ, PYTORCH_ENABLE_MPS_FALLBACK="1", PYTHONUNBUFFERED="1")
    log = open(log_path(), "a", encoding="utf-8")
    log.write(f"\n===== worker started {time.ctime()} =====\n")
    log.flush()
    _proc = subprocess.Popen([str(python), "-u", str(WORKER), str(folder)], cwd=folder, env=env,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
    _read(None, lambda stage: None)  # wait for {"ready": true}
    if _idle_watch is None:
        _idle_watch = threading.Thread(target=_let_go_when_idle, daemon=True)
        _idle_watch.start()


def _read(job_id, on_stage) -> dict:
    """Read the worker's answers until this job is done (or failed)."""
    with open(log_path(), "a", encoding="utf-8") as log:
        for line in _proc.stdout:
            if not line.startswith(MARK):
                log.write(line)  # TRELLIS talking
                continue
            msg = json.loads(line[len(MARK):])
            if msg.get("ready"):
                return msg
            if msg.get("id") != job_id:
                continue
            if "stage" in msg:
                on_stage(msg["stage"])
            elif msg.get("done"):
                return msg
            elif "error" in msg:
                raise TrellisError(msg["error"])
    if _stopping:
        raise _Stopped()
    raise TrellisError(f"TRELLIS stopped unexpectedly. Its log: {log_path()}")


_stopping = False


def make(job_id: str, image: str, out: str, seed: int, on_stage) -> dict:
    """Make one textured GLB at out. on_stage(stage): loading, shape, texture, saving."""
    global _last_used, _stopping
    if why := problem():
        raise TrellisError(why)
    with _lock:
        _stopping = False
        if not loaded():
            on_stage("loading")
            _start()
        cfg = settings.get()
        request = {"id": job_id, "image": image, "out": out, "seed": seed,
                   "texture_size": cfg["texture_size"], "pipeline_type": cfg["pipeline_type"]}
        _proc.stdin.write(json.dumps(request) + "\n")
        _proc.stdin.flush()
        try:
            return _read(job_id, on_stage)
        finally:
            _last_used = time.time()


def stop() -> None:
    """Stop the worker now (a job being made stops with it). The next job starts it again."""
    global _proc, _stopping
    if loaded():
        _stopping = True
        _proc.terminate()
        try:
            _proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None


def _let_go_when_idle() -> None:
    while True:
        time.sleep(30)
        idle = settings.get()["idle_minutes"] * 60
        if loaded() and not _lock.locked() and time.time() - _last_used > idle:
            with _lock:
                stop()
