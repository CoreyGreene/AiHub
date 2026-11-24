"""Pipelines: saved bulk files chained, each step working on the one before's output.

A pipeline is a name and its steps, each a saved bulk file (saved/pipelines/<name>.json, see saved.py). Running one
takes an input folder and an output folder. Step 1 works on (a copy of) the input folder and puts the files it
changed in <output>/1-<step>; step 2 works on that folder and puts what it changed in <output>/2-<step>; and so on.
Every step is an ordinary bulk run with an output folder, so the originals are never touched and each step can be
watched, stopped and undone on the Bulk tab like any run.

The pipeline's own record (pipeline-runs/<id>.json) says which step it's on; when a step's run finishes, bulk.py
tells us and the next step starts. A step that's stopped stops the pipeline (Carry on picks it up again).
"""

import json
import threading
import time
import uuid
from pathlib import Path

from . import bulk, saved, settings, tools


class PipelineError(Exception):
    pass


_lock = threading.RLock()
_runs: dict[str, dict] = {}
_loaded = False


def check(data) -> None:
    """Raise if this isn't a pipeline that could run: a name and steps that are saved bulk files."""
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list) or not data["steps"]:
        raise PipelineError("A pipeline needs at least one step.")
    have = {b["id"] for b in saved.listing("bulk")}
    for n, step in enumerate(data["steps"], 1):
        if not isinstance(step, str) or step not in have:
            raise PipelineError(f"Step {n} ({step}) isn't in the Saved list any more.")


# ---------- runs ----------

def _path(run_id: str) -> Path:
    return settings.folder("pipelines_dir") / f"{run_id}.json"


def _save(run: dict):
    path = _path(run["id"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(run, indent=1), encoding="utf-8")
    tmp.replace(path)


def _load_all():
    """Read the saved pipeline runs once. One that was going when CodeAi stopped is paused (its step's run is too)."""
    global _loaded
    if _loaded:
        return
    for p in settings.folder("pipelines_dir").glob("*.json"):
        try:
            run = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if run["status"] == "running":
            run["status"] = "paused"
            _save(run)
        _runs[run["id"]] = run
    _loaded = True


def listing() -> list[dict]:
    with _lock:
        _load_all()
        return [_view(r) for r in sorted(_runs.values(), key=lambda r: r["created"], reverse=True)]


def get(run_id: str) -> dict | None:
    with _lock:
        _load_all()
        run = _runs.get(run_id)
        return _view(run) if run else None


def _view(run: dict) -> dict:
    """The record plus each step's run as it stands now (counts, status)."""
    out = {k: v for k, v in run.items() if k != "steps"}
    out["steps"] = []
    for step in run["steps"]:
        s = {k: v for k, v in step.items() if k != "file"}
        r = bulk.get(step["run"]) if step.get("run") else None
        if r:
            counts = {}
            for i in r["items"]:
                counts[i["status"]] = counts.get(i["status"], 0) + 1
            s.update(run_status=r["status"], counts=counts, total=len(r["items"]), copied=len(r.get("copied", [])),
                     seconds=r["seconds"])
        out["steps"].append(s)
    return out


def start(pipeline_id: str, input_folder: str, output_folder: str, model: str = "", thinking: str = "",
          source: str = "you") -> dict:
    with _lock:
        _load_all()
    try:
        definition = json.loads(saved.get("pipeline", pipeline_id)["text"])
    except saved.SavedError as err:
        raise PipelineError(str(err))
    check(definition)
    where = tools.inside_allowed(input_folder)
    if where is None:
        raise PipelineError("Pick an input folder inside your allowed folders.")
    out = tools.inside_allowed(output_folder)
    if out is None:
        raise PipelineError("Pick an output folder inside your allowed folders.")
    if out == where or where in out.parents:
        raise PipelineError("The output folder can't be inside the input folder.")
    steps = []
    for n, name in enumerate(definition["steps"], 1):
        file = json.loads(saved.get("bulk", name)["text"])  # a copy now: editing the saved one later won't change this run
        title = str(file.get("name") or name)
        steps.append({"n": n, "bulk": name, "name": title, "file": file, "run": None, "status": "waiting",
                      "folder": "", "output": str(out / f"{n}-{saved.slug(title)}")})
    run = {"id": uuid.uuid4().hex[:12], "pipeline": pipeline_id, "name": definition.get("name") or pipeline_id,
           "input": str(where), "output": str(out), "model": model, "thinking": thinking, "source": source,
           "status": "running", "created": time.time(), "finished": None, "current": 1, "error": "", "steps": steps}
    with _lock:
        _runs[run["id"]] = run
        _start_step(run)
        _save(run)
    return _view(run)


def _start_step(run: dict):
    """Start the current step: on the input folder (step 1) or the step before's output. Holds _lock."""
    step = run["steps"][run["current"] - 1]
    step["folder"] = run["input"] if step["n"] == 1 else run["steps"][step["n"] - 2]["output"]
    Path(step["output"]).mkdir(parents=True, exist_ok=True)
    Path(step["folder"]).mkdir(parents=True, exist_ok=True)  # a step before that changed nothing made no folder
    try:
        r = bulk.start(step["file"], step["folder"], run["model"], run["thinking"], None,
                       f"{run['name']} · {step['n']}. {step['name']}", run["source"], step["output"])
    except bulk.BulkError as err:
        step["status"] = "error"
        run.update(status="error", error=f"Step {step['n']} couldn't start: {err}", finished=time.time())
        return
    step.update(run=r["id"], status="running")


def _step_finished(info: dict):
    """bulk.py: a run finished or stopped. If it's a pipeline's current step, go on to the next (or stop)."""
    with _lock:
        _load_all()
        for run in _runs.values():
            if run["status"] not in ("running", "paused"):
                continue
            step = run["steps"][run["current"] - 1]
            if step.get("run") != info["id"]:
                continue
            if info["status"] == "done":
                step["status"] = "done"
                if run["current"] < len(run["steps"]):
                    run["current"] += 1
                    if run["status"] == "running":
                        _start_step(run)
                else:
                    run.update(status="done", finished=time.time())
            elif info["status"] == "stopped":
                step["status"] = "stopped"
                run["status"] = "stopped"
            _save(run)


bulk.on_finish(_step_finished)


def _find(run_id: str) -> dict:
    _load_all()
    run = _runs.get(run_id)
    if run is None:
        raise PipelineError("That pipeline run is gone.")
    return run


def stop(run_id: str) -> dict:
    with _lock:
        run = _find(run_id)
        step = run["steps"][run["current"] - 1]
        if run["status"] in ("running", "paused"):
            if step.get("run") and step["status"] == "running":
                try:
                    bulk.stop(step["run"])  # its finish comes back through _step_finished
                except bulk.BulkError:
                    pass
            run["status"] = "stopped"
            if step["status"] == "running":
                step["status"] = "stopped"
            _save(run)
        return _view(run)


def carry_on(run_id: str) -> dict:
    """Start a stopped or paused pipeline again: its current step's run carries on (or the step starts)."""
    with _lock:
        run = _find(run_id)
        if run["status"] == "running":
            raise PipelineError("It's still going.")
        if run["status"] == "done":
            raise PipelineError("It's finished.")
        step = run["steps"][run["current"] - 1]
        run.update(status="running", error="", finished=None)
        r = bulk.get(step["run"]) if step.get("run") else None
        if r is None:
            _start_step(run)
        elif r["status"] == "done":
            _save(run)
            threading.Thread(target=_step_finished, args=(bulk.summary(r),), daemon=True).start()
            return _view(run)
        else:
            try:
                bulk.carry_on(step["run"])
                step["status"] = "running"
            except bulk.BulkError as err:
                run.update(status="stopped", error=str(err))
        _save(run)
        return _view(run)


def delete(run_id: str) -> bool:
    """Delete a pipeline run's record. Its steps' runs stay on the Bulk tab; its output folders stay too."""
    with _lock:
        _load_all()
        run = _runs.get(run_id)
        if run is None:
            return False
        if run["status"] == "running":
            raise PipelineError("Stop it first.")
        del _runs[run_id]
        _path(run_id).unlink(missing_ok=True)
        return True
