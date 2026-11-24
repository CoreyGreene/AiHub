"""The queue. One job makes one version of one model; one at a time, in order.

A request only adds jobs and returns; the page asks for progress. A waiting job
can be removed; stopping the one being made stops TRELLIS (the next job starts
it again, which costs about a minute of loading).
"""

import queue as queue_module
import random
import threading
import time
import uuid

from . import library, settings, trellis

KEEP = 300  # finished jobs remembered for the page

_jobs: dict[str, dict] = {}
_order: list[str] = []
_queue: queue_module.Queue = queue_module.Queue()
_lock = threading.Lock()
_worker = None


class QueueFull(Exception):
    pass


def _active() -> int:
    return sum(1 for j in _jobs.values() if j["status"] in ("waiting", "working"))


def submit(slug: str, name: str, picture: str, versions: int, batch: str = "") -> list[str]:
    """Queue versions of a model from one of its pictures. batch: a bulk run's id."""
    global _worker
    with _lock:
        most = settings.get()["max_queue"]
        if _active() + versions > most:
            raise QueueFull(f"The queue is full ({most} jobs). Try again when some are done.")
    ids = []
    for _ in range(versions):
        seed = random.randrange(2**31)
        version = library.new_version(slug, picture, seed)
        job_id = uuid.uuid4().hex
        with _lock:
            _jobs[job_id] = {"id": job_id, "slug": slug, "name": name, "version": version["id"],
                             "picture": picture, "seed": seed, "status": "waiting", "stage": "",
                             "added": time.time(), "started": None, "seconds": None, "message": "",
                             "batch": batch, "stop": False}
            _order.append(job_id)
            if _worker is None:
                _worker = threading.Thread(target=_work, daemon=True)
                _worker.start()
        _queue.put(job_id)
        ids.append(job_id)
    return ids


def _forget_old() -> None:
    done = [j for j in _order if _jobs[j]["status"] not in ("waiting", "working")]
    for job_id in done[:-KEEP] if len(done) > KEEP else []:
        _order.remove(job_id)
        del _jobs[job_id]


def _work() -> None:
    while True:
        job_id = _queue.get()
        with _lock:
            job = _jobs.get(job_id)
            if job is None or job["stop"]:
                continue
            job.update(status="working", started=time.time())
        library.update_version(job["slug"], job["version"], status="working")
        picture, glb = library.paths(job["slug"], job["version"], job["picture"])

        def on_stage(stage):
            with _lock:
                job["stage"] = stage

        try:
            result = trellis.make(job_id, str(picture), str(glb), job["seed"], on_stage)
            library.update_version(job["slug"], job["version"], status="done", seconds=result["seconds"],
                                   faces=result.get("faces"))
            with _lock:
                job.update(status="done", seconds=result["seconds"], stage="")
        except trellis._Stopped:
            _drop_version(job)
            with _lock:
                job.update(status="stopped", stage="", message="Stopped.")
        except Exception as err:  # noqa: BLE001  shown on the page, the queue goes on
            message = str(err) if isinstance(err, (trellis.TrellisError, library.LibraryError)) else \
                f"{type(err).__name__}: {err}"
            library.update_version(job["slug"], job["version"], status="failed", message=message)
            with _lock:
                job.update(status="failed", stage="", message=message)
        with _lock:
            _forget_old()


def _drop_version(job: dict) -> None:
    library.update_version(job["slug"], job["version"], status="failed")
    try:
        library.delete_version(job["slug"], job["version"])
    except library.LibraryError:
        pass


def stop(job_id: str) -> None:
    """Remove a waiting job, or stop the one being made."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None or job["status"] not in ("waiting", "working"):
            return
        job["stop"] = True
        working = job["status"] == "working"
        if not working:
            job.update(status="stopped", message="Removed before it started.")
    if working:
        trellis.stop()
    else:
        _drop_version(job)


def stop_batch(batch: str) -> int:
    """Stop every job of a bulk run. Returns how many."""
    with _lock:
        ids = [j["id"] for j in _jobs.values() if j["batch"] == batch and j["status"] in ("waiting", "working")]
    for job_id in sorted(ids, key=lambda i: _jobs[i]["status"] == "working"):  # waiting ones first
        stop(job_id)
    return len(ids)


def listing() -> list[dict]:
    """Every job the page should show, oldest first, with how far along the queue is."""
    with _lock:
        out = []
        for job_id in _order:
            j = _jobs[job_id]
            item = {k: j[k] for k in ("id", "slug", "name", "version", "status", "stage", "seconds",
                                      "message", "batch", "added")}
            if j["status"] == "working" and j["started"]:
                item["running"] = round(time.time() - j["started"])
            out.append(item)
        return out


def summary() -> dict:
    with _lock:
        waiting = sum(1 for j in _jobs.values() if j["status"] == "waiting")
        working = next((j for j in _jobs.values() if j["status"] == "working"), None)
        recent = [j["seconds"] for j in _jobs.values() if j["status"] == "done" and j["seconds"]][-10:]
    return {"waiting": waiting, "working": working["name"] if working else None,
            "stage": working["stage"] if working else "",
            "typical_seconds": round(sum(recent) / len(recent)) if recent else None,
            "loaded": trellis.loaded()}
