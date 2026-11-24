"""The web server: serves the page in web/ and a small JSON API under /api.

The same API is for the page and, later, for Claude (an MCP connector that calls it): ask, follow the answer, see the
queue, stop, and read past conversations.
"""

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import bulk, history, jobs, memory, models, pipelines, saved, settings, tools

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
# Changes on every server start: the page asks for app.css and main.js with it attached, so a restart always gets
# fresh files, never old cached ones.
STARTED = str(int(time.time()))

app = FastAPI(title="CodeAi")


@app.middleware("http")
async def no_stale_page(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/", response_class=HTMLResponse)
async def page() -> str:
    return (WEB_DIR / "index.html").read_text(encoding="utf-8").replace("{{v}}", STARTED)


@app.get("/api/status")
async def status() -> dict:
    """The line at the top: memory, the model in memory, and the queue."""
    return {"memory": memory.status(), "model": models.loaded(), "queue": jobs.queue()}


@app.get("/api/models")
async def model_list() -> dict:
    found = [{"id": m["id"], "name": m["name"], "note": m.get("note", ""), "thinking": settings.thinking(m)}
             for m in settings.models()]
    return {"models": found, "default": found[0]["id"] if found else None,
            "folders": tools.folders()}


class AskRequest(BaseModel):
    prompt: str
    model: str = ""
    conversation: str = ""  # empty = a new conversation
    source: str = "you"     # who's asking: "you" (the page) or "claude"
    thinking: str = ""      # the model's thinking level (GET /api/models lists each model's); "" = its default
    can_edit: bool = False  # may it change files for this question (backed up first; Undo puts them back)


@app.post("/api/ask")
async def ask(req: AskRequest) -> dict:
    """Ask a question, in a new conversation or to carry one on. Answers {job, conversation} at once; follow the
    answer with GET /api/jobs/{job}."""
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Type a question first.")
    model_id = req.model or (settings.models() or [{}])[0].get("id")
    if not model_id or settings.model(model_id) is None:
        raise HTTPException(400, "That model isn't on this computer.")
    if req.conversation:
        if history.get(req.conversation) is None:
            raise HTTPException(404, "That conversation is gone.")
        if jobs.for_conversation(req.conversation):
            raise HTTPException(409, "It's still answering the last question in this conversation.")
        conv_id = req.conversation
    else:
        conv_id = history.create(prompt, model_id)["id"]
    source = "claude" if req.source == "claude" else "you"
    history.add(conv_id, {"role": "user", "content": prompt, "from": source, "can_edit": req.can_edit,
                          "time": time.time()})
    try:
        job_id = jobs.submit(conv_id, model_id, prompt, source, req.thinking, req.can_edit)
    except jobs.QueueFull as err:
        raise HTTPException(429, str(err))
    return {"job": job_id, "conversation": conv_id}


@app.get("/api/jobs/{job_id}")
async def job(job_id: str) -> dict:
    found = jobs.status(job_id)
    if found is None:
        raise HTTPException(404, "No such question (finished ones are forgotten after a while: see History).")
    return found


@app.get("/api/queue")
async def queue() -> list:
    return jobs.listing()


@app.delete("/api/queue/{job_id}")
async def stop(job_id: str) -> dict:
    if not jobs.remove(job_id):
        raise HTTPException(404, "That question isn't waiting or being answered.")
    return {"stopped": True}


@app.get("/api/history")
async def history_list() -> list:
    return history.listing()


@app.get("/api/history/{conv_id}")
async def history_one(conv_id: str) -> dict:
    conv = history.get(conv_id)
    if conv is None:
        raise HTTPException(404, "That conversation is gone.")
    return {**conv, "job": jobs.for_conversation(conv_id)}


@app.delete("/api/history")
async def history_delete_all() -> dict:
    """Delete every conversation, except one still being answered (stop it first). Their file backups stay, so a
    change can still be put back by hand from backups/."""
    deleted = kept = 0
    for c in history.listing():
        if jobs.for_conversation(c["id"]):
            kept += 1
        elif history.delete(c["id"]):
            deleted += 1
    return {"deleted": deleted, "kept": kept}


@app.delete("/api/history/{conv_id}")
async def history_delete(conv_id: str) -> dict:
    if jobs.for_conversation(conv_id):
        raise HTTPException(409, "It's still answering in this conversation. Stop it first.")
    if not history.delete(conv_id):
        raise HTTPException(404, "That conversation is gone.")
    return {"deleted": True}


@app.post("/api/history/{conv_id}/undo/{index}")
async def undo(conv_id: str, index: int) -> dict:
    """Put back the files one answer changed (message number `index` in the conversation)."""
    conv = history.get(conv_id)
    if conv is None or not 0 <= index < len(conv["messages"]):
        raise HTTPException(404, "That answer is gone.")
    message = conv["messages"][index]
    if not message.get("changes"):
        raise HTTPException(400, "That answer didn't change any files.")
    if message.get("undone"):
        raise HTTPException(409, "Its changes were already undone.")
    notes = tools.undo(message["changes"])
    history.update_message(conv_id, index, undone=True, undo_notes=notes)
    return {"undone": True, "notes": notes}


# ---------- Bulk: one task over a list of items, each with a fresh memory ----------

class BulkRequest(BaseModel):
    file: dict               # the bulk file: {prompt, items, ...} (bulk.py says what it can hold)
    folder: str = ""         # these win over the file's own, when given
    model: str = ""
    thinking: str = ""
    can_change_files: bool | None = None
    output: str = ""         # a folder to copy every changed file into (optional)
    name: str = ""
    source: str = "you"


def _bulk(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except bulk.BulkError as err:
        raise HTTPException(400, str(err))


@app.get("/api/bulk")
async def bulk_list() -> list:
    return bulk.listing()


@app.post("/api/bulk")
async def bulk_start(req: BulkRequest) -> dict:
    """Start a run from a bulk file. The request's folder, model, thinking and can_change_files win over the file's."""
    return _bulk(bulk.start, req.file, req.folder, req.model, req.thinking, req.can_change_files, req.name,
                 "claude" if req.source == "claude" else "you", req.output)


class OutputRequest(BaseModel):
    path: str


@app.post("/api/bulk/{run_id}/output")
async def bulk_output(run_id: str, req: OutputRequest) -> dict:
    """Copy a run's changed files into a folder (and keep doing so as it goes)."""
    return _bulk(bulk.set_output, run_id, req.path)


@app.get("/api/browse")
async def browse(path: str = "", ext: str = "") -> dict:
    """The page's folder picker: folders (and ext files, e.g. .json) inside the allowed folders."""
    try:
        return tools.browse(path, ext)
    except tools.ToolError as err:
        raise HTTPException(400, str(err))


@app.get("/api/bulk/file")
async def bulk_file(path: str) -> dict:
    """A bulk file's text, from inside the allowed folders (the page's Open a bulk file)."""
    file = Path(path).expanduser().resolve()
    if file.suffix.lower() != ".json" or not file.is_file() or tools.inside_allowed(str(file.parent)) is None:
        raise HTTPException(400, "Pick a .json file inside your allowed folders.")
    if file.stat().st_size > 5_000_000:
        raise HTTPException(400, "That file is over 5 MB: too big for a bulk file.")
    return {"name": file.stem, "path": str(file), "text": file.read_text(encoding="utf-8", errors="replace")}


# ---------- the Saved list: bulk files and pipelines kept to run again ----------

class SaveRequest(BaseModel):
    name: str
    text: str


def _saved(fn, *args):
    try:
        return fn(*args)
    except (saved.SavedError, bulk.BulkError, pipelines.PipelineError) as err:
        raise HTTPException(400, str(err))


def _kind(kind: str) -> str:
    if kind not in ("bulk", "pipeline"):
        raise HTTPException(404, "There's nothing like that saved.")
    return kind


@app.get("/api/saved/{kind}")
async def saved_list(kind: str) -> list:
    return saved.listing(_kind(kind))


@app.get("/api/saved/{kind}/{name}")
async def saved_get(kind: str, name: str) -> dict:
    return _saved(saved.get, _kind(kind), name)


@app.post("/api/saved/{kind}")
async def saved_save(kind: str, req: SaveRequest) -> dict:
    """Save a bulk file (it must be one that could run) or a pipeline (its steps must be saved bulk files)."""
    check = bulk.check_file if _kind(kind) == "bulk" else pipelines.check
    return _saved(saved.save, kind, req.name, req.text, check)


@app.delete("/api/saved/{kind}/{name}")
async def saved_delete(kind: str, name: str) -> dict:
    if not _saved(saved.delete, _kind(kind), name):
        raise HTTPException(404, "That's already gone.")
    return {"deleted": True}


# ---------- Pipelines: saved bulk files chained, each step on the one before's output ----------

class PipelineRequest(BaseModel):
    pipeline: str            # a saved pipeline's id (GET /api/saved/pipeline)
    input: str               # the folder step 1 works on (a copy: the originals aren't touched)
    output: str              # each step's changed files go in <output>/<n>-<step>
    model: str = ""          # empty = each bulk file's own
    thinking: str = ""
    source: str = "you"


@app.get("/api/pipelines")
async def pipeline_list() -> list:
    return pipelines.listing()


@app.post("/api/pipelines")
async def pipeline_start(req: PipelineRequest) -> dict:
    return _saved(pipelines.start, req.pipeline, req.input, req.output, req.model, req.thinking,
                  "claude" if req.source == "claude" else "you")


@app.get("/api/pipelines/{run_id}")
async def pipeline_one(run_id: str) -> dict:
    run = pipelines.get(run_id)
    if run is None:
        raise HTTPException(404, "That pipeline run is gone.")
    return run


@app.post("/api/pipelines/{run_id}/stop")
async def pipeline_stop(run_id: str) -> dict:
    return _saved(pipelines.stop, run_id)


@app.post("/api/pipelines/{run_id}/carry-on")
async def pipeline_carry_on(run_id: str) -> dict:
    return _saved(pipelines.carry_on, run_id)


@app.delete("/api/pipelines/{run_id}")
async def pipeline_delete(run_id: str) -> dict:
    if not _saved(pipelines.delete, run_id):
        raise HTTPException(404, "That's already gone.")
    return {"deleted": True}


@app.get("/api/bulk/{run_id}")
async def bulk_one(run_id: str) -> dict:
    run = bulk.get(run_id)
    if run is None:
        raise HTTPException(404, "That run is gone.")
    return run


@app.post("/api/bulk/{run_id}/stop")
async def bulk_stop(run_id: str) -> dict:
    return _bulk(bulk.stop, run_id)


@app.post("/api/bulk/{run_id}/carry-on")
async def bulk_carry_on(run_id: str, redo: bool = False) -> dict:
    return _bulk(bulk.carry_on, run_id, redo)


@app.post("/api/bulk/{run_id}/undo")
async def bulk_undo_all(run_id: str) -> dict:
    return _bulk(bulk.undo_all, run_id)


@app.post("/api/bulk/{run_id}/undo/{n}")
async def bulk_undo(run_id: str, n: int) -> dict:
    return {"notes": _bulk(bulk.undo_item, run_id, n)}


@app.delete("/api/bulk/{run_id}")
async def bulk_delete(run_id: str) -> dict:
    if not _bulk(bulk.delete, run_id):
        raise HTTPException(404, "That run is gone.")
    return {"deleted": True}


@app.post("/api/model/unload")
async def unload() -> dict:
    """Let go of the model now (Settings), unless it's answering."""
    if jobs.queue()["working"]:
        raise HTTPException(409, "It's answering a question. Stop it first.")
    models.unload()
    return {"unloaded": True}


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
