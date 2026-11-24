"""Experiments: batches of prompts, each with its own model, made one after another to compare.

An experiment is a JSON file in the experiments folder (server/experiment/, personal, never committed):

    {"name": "Robots", "seed": 1234,
     "batches": [{"name": "Qwen 8-bit", "model": "Qwen-Image-2512-8bit", "prompts": ["a robot", ...],
                  "count": 1, "width": 0, "height": 0, "steps": 0, "guidance": 0, "negative": ""}]}

0 (or left out) means the model's own default. Every batch uses the same seeds (prompt n, picture k:
seed + n * 100 + (k - 1) * 1000), so the same prompt in two batches differs only by the model.

The models to choose from: every SDXL file in models_dir, plus the folders listed in settings.json
"experiments" → "models" that are here (Qwen-Image, FLUX.2 klein through mflux, on a Mac).

Start queues every batch's pictures in order, so they're made one at a time, batch after batch. Each
run gets a folder: outputs/experiments/<run>/<n>-<batch>/ with the pictures (and their settings
beside them), and run.json saying what was asked.
"""

import json
import random
import re
import shutil
import sys
import time
from datetime import datetime

from . import generation, jobs, pictures, settings

SDXL_DEFAULTS = {"width": 1024, "height": 1024, "steps": 28, "guidance": 6.0}
SIZE_LIMIT = 2048


class ExperimentError(Exception):
    pass


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "experiment"


# ---------- models ----------

def models() -> list[dict]:
    """Every model a batch can use: id, name, here (its files are in models_dir), its defaults."""
    folder = settings.folder("models_dir")
    out = []
    if sys.platform == "darwin":  # mflux is MLX: Apple Silicon only
        for m in settings.get().get("experiments", {}).get("models", []):
            out.append({"id": m["folder"], "name": m["name"], "backend": "mflux", "kind": m["kind"],
                        "quantize": m.get("quantize"), "here": (folder / m["folder"]).is_dir(),
                        "negative": m["kind"] != "flux2-klein-4b",
                        "defaults": {k: m[k] for k in ("width", "height", "steps", "guidance")}})
    for name in generation.choices()["models"]:
        out.append({"id": name, "name": name.rsplit(".", 1)[0], "backend": "diffusers-sdxl", "here": True,
                    "negative": True, "defaults": dict(SDXL_DEFAULTS)})
    return out


def _model(model_id: str) -> dict:
    found = next((m for m in models() if m["id"] == model_id), None)
    if found is None:
        raise ExperimentError(f"There's no model called {model_id or '(none)'}.")
    if not found["here"]:
        raise ExperimentError(f"{found['name']} isn't here yet: put its folder in the models folder.")
    return found


def _theme(model: dict, batch: dict) -> dict:
    """What generation.generate() needs: the model, the batch's settings (or the model's), no words around
    the prompt."""
    value = lambda key: batch.get(key) or model["defaults"][key]  # noqa: E731
    theme = {"name": model["name"], "backend": model["backend"], "model": model["id"], "prompt": "{prompt}",
             "negative": batch.get("negative", "") if model["negative"] else "",
             **{key: value(key) for key in ("width", "height", "steps", "guidance")}}
    if model["backend"] == "mflux":
        theme.update(kind=model["kind"], quantize=model["quantize"])
    else:
        theme.update(model_config=settings.get()["custom"]["model_config"], scheduler="euler_a")
    return theme


# ---------- saved experiments ----------

def _folder():
    path = settings.folder("experiments_dir")
    path.mkdir(parents=True, exist_ok=True)
    return path


def listing() -> list[dict]:
    out = []
    for path in sorted(_folder().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"id": path.stem, "name": data.get("name", path.stem), "batches": len(data.get("batches", []))})
    return out


def get(exp_id: str) -> dict | None:
    if not re.fullmatch(r"[a-z0-9-]+", exp_id or ""):
        return None
    path = _folder() / f"{exp_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"id": exp_id, "name": data.get("name", exp_id), "seed": data.get("seed", 0), "batches": data.get("batches", [])}


def _number(value, low, high, what) -> float:
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        raise ExperimentError(f"{what} should be a number.")
    if n and not low <= n <= high:
        raise ExperimentError(f"{what} should be between {low} and {high} (or empty for the model's own).")
    return n


def _clean(data: dict) -> dict:
    """Check an experiment from the page and tidy it. Raises ExperimentError."""
    name = " ".join(str(data.get("name", "")).split())
    if not name:
        raise ExperimentError("Give the experiment a name.")
    batches = []
    for n, b in enumerate(data.get("batches") or [], 1):
        prompts = [" ".join(str(p).split()) for p in b.get("prompts") or []]
        prompts = [p for p in prompts if p]
        try:
            count = int(b.get("count") or 1)
            width, height = (int(_number(b.get(k), 256, SIZE_LIMIT, f"Batch {n}: {k}")) for k in ("width", "height"))
            steps = int(_number(b.get("steps"), 1, 150, f"Batch {n}: steps"))
            guidance = _number(b.get("guidance"), 0.1, 30, f"Batch {n}: guidance")
        except ValueError:
            raise ExperimentError(f"Batch {n}: how many pictures should be a number.")
        if not 1 <= count <= 20:
            raise ExperimentError(f"Batch {n}: 1 to 20 pictures a prompt.")
        if width % 16 or height % 16:
            raise ExperimentError(f"Batch {n}: width and height should be steps of 16 (1024, 1328 ...).")
        batches.append({"name": " ".join(str(b.get("name", "")).split()), "model": str(b.get("model", "")),
                        "prompts": prompts, "count": count, "width": width, "height": height, "steps": steps,
                        "guidance": guidance, "negative": " ".join(str(b.get("negative", "")).split())})
    seed = data.get("seed")
    seed = int(seed) if str(seed or "").isdigit() else random.randrange(1, 10**6)
    return {"name": name, "seed": seed, "batches": batches}


def save(exp_id: str, data: dict) -> str:
    """Save an experiment (exp_id "" makes a new one, named after itself). Returns its id."""
    clean = _clean(data)
    folder = _folder()
    if not exp_id:
        base = _slug(clean["name"])
        exp_id, n = base, 1
        while (folder / f"{exp_id}.json").exists():
            n += 1
            exp_id = f"{base}-{n}"
    elif get(exp_id) is None:
        raise ExperimentError("That experiment isn't there any more.")
    path = folder / f"{exp_id}.json"
    spare = path.with_suffix(".json.saving")
    spare.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    spare.replace(path)
    return exp_id


def delete(exp_id: str) -> bool:
    if get(exp_id) is None:
        return False
    (_folder() / f"{exp_id}.json").unlink()
    return True


# ---------- runs ----------

def _run_dir(run_id: str):
    if not re.fullmatch(r"[a-z0-9-]+", run_id or ""):
        return None
    path = pictures.experiments() / run_id
    return path if (path / "run.json").is_file() else None


def _read_run(run_id: str) -> dict | None:
    path = _run_dir(run_id)
    if path is None:
        return None
    try:
        return json.loads((path / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_run(run: dict):
    path = pictures.experiments() / run["id"] / "run.json"
    spare = path.with_suffix(".json.saving")
    spare.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    spare.replace(path)


def start(exp_id: str) -> str:
    """Queue every batch's pictures, in order. Returns the run's id (its folder's name)."""
    exp = get(exp_id)
    if exp is None:
        raise ExperimentError("That experiment isn't there any more.")
    batches = [b for b in exp["batches"] if b["prompts"]]
    if not batches:
        raise ExperimentError("Add a batch with at least one prompt first.")
    chosen = [_model(b["model"]) for b in batches]  # every model checked before anything is queued
    needed = sum(len(b["prompts"]) for b in batches)
    if needed > jobs.room():
        raise ExperimentError(f"The queue has room for {jobs.room()} more prompts; this needs {needed}. "
                              "Try again when some are done.")
    run_id = f"{_slug(exp['name'])}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    root = pictures.experiments() / run_id
    root.mkdir(parents=True)
    run = {"id": run_id, "experiment": exp_id, "name": exp["name"], "seed": exp["seed"], "created": time.time(),
           "stopped": False, "batches": []}
    for n, (batch, model) in enumerate(zip(batches, chosen), 1):
        theme = _theme(model, batch)
        folder_name = f"{n}-{_slug(batch['name'] or model['name'])}"
        folder = root / folder_name
        folder.mkdir()
        job_ids = []
        for i, prompt in enumerate(batch["prompts"]):
            extra = {"experiment": run_id, "batch": n, "prompt_number": i + 1}
            job_ids.append(jobs.submit("", theme, prompt, batch["count"], folder=folder,
                                       seed=exp["seed"] + i * 100, extra=extra))
        run["batches"].append({
            "n": n, "name": batch["name"] or model["name"], "model": model["id"], "model_name": model["name"],
            "folder": folder_name, "prompts": batch["prompts"], "count": batch["count"], "jobs": job_ids,
            "settings": {k: theme[k] for k in ("width", "height", "steps", "guidance", "negative")},
        })
    _write_run(run)
    return run_id


def _batch_view(run: dict, batch: dict) -> dict:
    folder = pictures.experiments() / run["id"] / batch["folder"]
    made = []
    for path in folder.glob("*.json"):
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (folder / f"{info.get('id')}.png").is_file():
            made.append(info)
    made.sort(key=lambda i: (i.get("prompt_number", 0), i.get("number", 0)))
    states = [jobs.status(j) for j in batch["jobs"]]
    working = next((s for s in states if s and s["status"] == "working"), None)
    if working:
        status = "working"
    elif any(s and s["status"] == "waiting" for s in states):
        status = "waiting"
    elif len(made) >= len(batch["prompts"]) * batch["count"]:
        status = "done"
    else:
        status = "stopped" if run["stopped"] or not any(states) else "done"
    problems = sorted({s["message"] for s in states if s and s["status"] in ("failed", "blocked") and s.get("message")})
    timed = [i["seconds"] for i in made if "seconds" in i and not i.get("loaded")]
    loading = [i["seconds"] for i in made if "seconds" in i and i.get("loaded")]
    return {
        **{k: batch[k] for k in ("n", "name", "model", "model_name", "folder", "prompts", "count", "settings")},
        "path": str(folder),
        "status": status,
        "stage": working.get("stage") if working else "",
        "step": working.get("step", 0) if working else 0,
        "steps": working.get("steps", 0) if working else 0,
        "made": len(made),
        "total": len(batch["prompts"]) * batch["count"],
        "seconds": round(sum(timed) / len(timed), 1) if timed else None,  # a picture, model already loaded
        "first_seconds": loading[0] if loading else None,  # the first one, with loading the model
        "problems": problems,
        "pictures": [{"id": i["id"], "image": f"api/pictures/{i['id']}", "prompt_number": i.get("prompt_number", 0),
                      "number": i.get("number", 1), "seed": i.get("seed"), "seconds": i.get("seconds")} for i in made],
    }


def run_view(run_id: str) -> dict | None:
    run = _read_run(run_id)
    if run is None:
        return None
    batches = [_batch_view(run, b) for b in run["batches"]]
    running = any(b["status"] in ("working", "waiting") for b in batches)
    return {"id": run["id"], "experiment": run["experiment"], "name": run["name"], "seed": run["seed"],
            "created": run["created"], "path": str(pictures.experiments() / run["id"]),
            "status": "running" if running else ("stopped" if run["stopped"] else "done"), "batches": batches}


def runs(exp_id: str = "") -> list[dict]:
    """Every run (or one experiment's), newest first: a summary each."""
    root = pictures.experiments()
    out = []
    for path in root.glob("*/run.json") if root.is_dir() else []:
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if exp_id and run.get("experiment") != exp_id:
            continue
        view = run_view(run["id"])
        if view:
            out.append({k: view[k] for k in ("id", "experiment", "name", "created", "status")}
                       | {"batches": len(view["batches"]), "made": sum(b["made"] for b in view["batches"]),
                          "total": sum(b["total"] for b in view["batches"])})
    return sorted(out, key=lambda r: r["created"], reverse=True)


def stop(run_id: str) -> bool:
    """Take the run's waiting pictures out of the queue; the one being made stops after its step."""
    run = _read_run(run_id)
    if run is None:
        return False
    for batch in run["batches"]:
        for job_id in batch["jobs"]:
            jobs.remove(job_id)
    run["stopped"] = True
    _write_run(run)
    return True


def delete_run(run_id: str) -> bool:
    """Delete a run's folder and every picture in it (not while it's running)."""
    view = run_view(run_id)
    if view is None:
        return False
    if view["status"] == "running":
        raise ExperimentError("Stop it first.")
    shutil.rmtree(pictures.experiments() / run_id)
    return True
