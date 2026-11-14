"""The picture queue. Making a picture takes a while, so a request only
adds a job and returns at once; the page then asks for its progress.

One worker makes one picture at a time (one graphics card, one model).
"""

import queue
import threading
import traceback
import uuid

from . import generation, pictures

KEEP = 50  # finished jobs remembered for the page to collect

_jobs: dict[str, dict] = {}
_queue: queue.Queue = queue.Queue()
_lock = threading.Lock()
_worker = None


def submit(theme_id: str, theme: dict, prompt: str, count: int = 1) -> str:
    global _worker
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {
            "status": "waiting", "theme_id": theme_id, "theme": theme, "prompt": prompt,
            "count": count, "number": 0, "pictures": [], "blocked": 0,
        }
        if _worker is None:
            _worker = threading.Thread(target=_work, daemon=True)
            _worker.start()
    _queue.put(job_id)
    return job_id


def status(job_id: str) -> dict | None:
    """What the page sees: status, stage, step, steps, count, number (which
    picture is being made), pictures made so far, blocked, ahead, message."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        out = {k: v for k, v in job.items() if k not in ("theme", "prompt", "theme_id")}
        out["pictures"] = list(job["pictures"])
        if job["status"] == "waiting":
            out["ahead"] = sum(
                1 for j in _jobs.values() if j["status"] in ("waiting", "working") and j is not job
            )
        return out


def _update(job_id: str, **changes):
    with _lock:
        _jobs[job_id].update(changes)


def _work():
    while True:
        job_id = _queue.get()
        job = _jobs[job_id]
        _update(job_id, status="working", stage="starting")
        try:
            for number in range(1, job["count"] + 1):
                _update(job_id, number=number)
                try:
                    image, details = generation.generate(
                        job["theme"],
                        job["prompt"],
                        lambda stage, done, total: _update(job_id, stage=stage, step=done, steps=total),
                    )
                except generation.Blocked:
                    _update(job_id, blocked=job["blocked"] + 1)
                    continue
                pic_id = pictures.keep_new(
                    image, {"theme": job["theme_id"], "prompt": job["prompt"], **details}
                )
                with _lock:
                    job["pictures"].append({"picture": pic_id, "image": f"api/pictures/{pic_id}"})
            if job["pictures"]:
                _update(job_id, status="done")
            else:
                _update(job_id, status="blocked", message=generation.BLOCKED_MESSAGE)
        except Exception as err:  # shown to the user; the full error goes to the console
            traceback.print_exc()
            _update(job_id, status="failed", message=str(err).splitlines()[0] if str(err) else type(err).__name__)
        _forget_old()


def _forget_old():
    with _lock:
        finished = [k for k, j in _jobs.items() if j["status"] not in ("waiting", "working")]
        for key in finished[:-KEEP]:
            del _jobs[key]
