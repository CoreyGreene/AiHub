"""The picture queue. Making a picture takes a while, so a request only
adds a job and returns at once; the page then asks for its progress.

One worker makes one job at a time (one graphics card, one model); the
rest wait in order. Jobs can be removed from the Settings page: a waiting
job is dropped, the one being made stops after its current step.
"""

import queue as queue_module
import threading
import traceback
import uuid

from . import generation, pictures, settings

KEEP = 50  # finished jobs remembered for the page to collect

_jobs: dict[str, dict] = {}
_queue: queue_module.Queue = queue_module.Queue()
_lock = threading.Lock()
_worker = None


class QueueFull(Exception):
    pass


class _Stopped(Exception):
    """Raised inside a picture when its job was removed."""


def submit(theme_id: str, theme: dict, prompt: str, count: int = 1) -> str:
    global _worker
    job_id = uuid.uuid4().hex
    with _lock:
        active = sum(1 for j in _jobs.values() if j["status"] in ("waiting", "working"))
        most = settings.get()["max_queue"]
        if active >= most:
            raise QueueFull(f"The queue is full ({most} jobs). Try again when some are done.")
        _jobs[job_id] = {
            "status": "waiting", "theme_id": theme_id, "theme": theme, "prompt": prompt,
            "count": count, "number": 0, "pictures": [], "blocked": 0, "stop": False,
        }
        if _worker is None:
            _worker = threading.Thread(target=_work, daemon=True)
            _worker.start()
    _queue.put(job_id)
    return job_id


def submit_edit(pic_id: str, instruction: str) -> str:
    """Queue a change to a picture (the Edit button). One picture comes out."""
    job_id = submit("", {"name": "Edit"}, instruction)
    with _lock:
        _jobs[job_id]["edit_of"] = pic_id
    return job_id


def status(job_id: str) -> dict | None:
    """What the page sees: status, stage, step, steps, count, number (which
    picture is being made), pictures made so far, blocked, ahead, message."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        out = {k: v for k, v in job.items() if k not in ("theme", "prompt", "theme_id", "stop", "edit_of")}
        out["pictures"] = list(job["pictures"])
        if job["status"] == "waiting":
            out["ahead"] = sum(
                1 for j in _jobs.values() if j["status"] in ("waiting", "working") and j is not job
            )
        return out


def queue() -> dict:
    """How busy the queue is, in pictures: one being made now, and how many
    are still to make after it (the rest of this job and every waiting job)."""
    with _lock:
        working = [j for j in _jobs.values() if j["status"] == "working"]
        waiting = sum(j["count"] for j in _jobs.values() if j["status"] == "waiting")
        waiting += sum(j["count"] - max(j["number"], 1) for j in working)
    return {"working": len(working), "waiting": waiting}


def listing() -> list[dict]:
    """Every job being made or waiting, in order, for the Settings page."""
    with _lock:
        return [
            {
                "id": job_id,
                "status": j["status"],
                "theme": j["theme"]["name"],
                "prompt": j["prompt"],
                "count": j["count"],
                "number": j["number"],
                "step": j.get("step", 0),
                "steps": j.get("steps", 0),
                "stopping": j["stop"],
            }
            for job_id, j in _jobs.items()
            if j["status"] in ("waiting", "working")
        ]


def remove(job_id: str) -> bool:
    """Take a job out of the queue. A waiting job is dropped at once; the
    one being made stops after its current step. False if it isn't there."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None or job["status"] not in ("waiting", "working"):
            return False
        if job["status"] == "waiting":
            job.update(status="removed", message="This picture job was removed from the queue.")
        else:
            job["stop"] = True
    return True


def _update(job_id: str, **changes):
    with _lock:
        _jobs[job_id].update(changes)


def _next_job() -> str:
    """Wait for the next job. If none comes for a while, free the graphics
    card's memory first, then keep waiting."""
    try:
        return _queue.get(timeout=settings.get()["unload_after_minutes"] * 60)
    except queue_module.Empty:
        generation.free_memory()
        return _queue.get()


def _work():
    while True:
        job_id = _next_job()
        job = _jobs[job_id]
        if job["status"] == "removed":  # taken out while it was waiting
            continue
        _update(job_id, status="working", stage="starting")

        def progress(stage, done, total):
            if job["stop"]:
                raise _Stopped()
            _update(job_id, stage=stage, step=done, steps=total)

        try:
            for number in range(1, job["count"] + 1):
                _update(job_id, number=number)
                try:
                    if job.get("edit_of"):
                        image, details = generation.edit(job["edit_of"], job["prompt"], progress)
                    else:
                        image, details = generation.generate(job["theme"], job["prompt"], progress)
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
        except _Stopped:
            # Pictures finished before the stop are still shown.
            if job["pictures"]:
                _update(job_id, status="done", stopped=True)
            else:
                _update(job_id, status="removed", message="This picture job was removed from the queue.")
        except Exception as err:  # shown to the user; the full error goes to the console
            traceback.print_exc()
            _update(job_id, status="failed", message=str(err).splitlines()[0] if str(err) else type(err).__name__)
        _forget_old()


def _forget_old():
    with _lock:
        finished = [k for k, j in _jobs.items() if j["status"] not in ("waiting", "working")]
        for key in finished[:-KEEP]:
            del _jobs[key]
