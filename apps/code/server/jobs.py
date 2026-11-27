"""The question queue. Answering takes a while, so asking only adds a job and returns at once; the page (or Claude,
over MCP later) then asks for its progress, and sees the answer grow as it's written.

One worker answers one question at a time (one model in memory); the rest wait in order. A job can be stopped: a
waiting one is dropped, the one being answered stops where it is, and what it wrote so far is kept.

A bulk item (bulk.py) is a job too, with no conversation: it brings its own fresh messages (so nothing from the item
before it), the one folder its tools may see, and on_done, called with its result instead of saving it in History.
"""

import json
import queue as queue_module
import threading
import time
import traceback
import uuid

from . import checks, history, models, settings, tools

KEEP = 50  # finished jobs remembered for the page to collect

_jobs: dict[str, dict] = {}
_queue: queue_module.Queue = queue_module.Queue()
_lock = threading.Lock()
_worker = None

ACTIVE = ("waiting", "loading", "thinking", "looking", "answering")


class QueueFull(Exception):
    pass


HIDDEN = ("stop", "changes", "messages", "on_done", "folders", "work_folder")  # kept off the page


def submit(conv_id: str | None, model_id: str, prompt: str, source: str = "you", thinking_level: str = "",
           can_edit: bool = False, bulk: dict | None = None, work_folder: str = "", can_run: bool = False,
           editor_path: str = "") -> str:
    """Queue a question in a conversation (the question is already saved in it). bulk: a bulk item's
    {run, index, messages, folders, on_done} instead of a conversation. work_folder: the conversation's one
    folder (Ask → Work folder): its tools see only that folder, like a bulk job's."""
    global _worker
    job_id = uuid.uuid4().hex
    with _lock:
        active = sum(1 for j in _jobs.values() if j["status"] in ACTIVE)
        most = settings.get()["max_queue"]
        if active >= most:
            raise QueueFull(f"The queue is full ({most} questions). Try again when some are answered.")
        _jobs[job_id] = {
            "status": "waiting", "conversation": conv_id, "model": model_id, "prompt": prompt, "source": source,
            "editor_path": editor_path,
            "thinking_level": thinking_level, "can_edit": can_edit, "changes": tools.Changes() if can_edit else None,
            "steps": [], "thinking": "", "answer": "", "tokens": 0, "seconds": 0, "per_second": 0, "message": "",
            "stop": threading.Event(), "queued": time.time(),
            "run": None, "index": None, "messages": None, "folders": None, "on_done": None, "max_steps": 0,
        }
        _jobs[job_id].update(bulk or {})
        if work_folder:
            # commands only with a work folder: the sandbox fences them to that one folder
            _jobs[job_id].update(folders=[work_folder], work_folder=work_folder, can_run=can_run)
        if _worker is None:
            _worker = threading.Thread(target=_work, daemon=True)
            _worker.start()
    _queue.put(job_id)
    return job_id


def status(job_id: str) -> dict | None:
    """What the page sees: status, the thinking and answer so far, speed, and how many are ahead of it."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        out = {k: v for k, v in job.items() if k not in HIDDEN}
        out["changes"] = job["changes"].summary() if job["changes"] else []
        out["stopping"] = job["stop"].is_set()
        out["steps"] = list(job["steps"])
        if job["status"] == "waiting":
            out["ahead"] = sum(1 for k, j in _jobs.items() if j["status"] in ACTIVE and j["queued"] < job["queued"])
        return out


def for_conversation(conv_id: str) -> str | None:
    """The job still working on this conversation, if any (so reopening it shows the answer being written)."""
    with _lock:
        return next((k for k, j in _jobs.items() if j["conversation"] == conv_id and j["status"] in ACTIVE), None)


def queue() -> dict:
    with _lock:
        working = sum(1 for j in _jobs.values() if j["status"] in ACTIVE[1:])
        waiting = sum(1 for j in _jobs.values() if j["status"] == "waiting")
    return {"working": working, "waiting": waiting}


def save_editor(path: str, text: str, revision: str) -> dict:
    # Hold the queue lock through the save so a question can't start in between.
    with _lock:
        if any(j["status"] in ACTIVE for j in _jobs.values()):
            raise tools.EditorConflict("Code AI is still working. Wait for it to finish before saving.")
        return tools.save_editor(path, text, revision)


def listing() -> list[dict]:
    """Every question being answered or waiting, in order."""
    with _lock:
        return [
            {"id": k, "status": j["status"], "model": j["model"], "prompt": j["prompt"], "source": j["source"],
             "can_edit": j["can_edit"], "run": j["run"], "index": j["index"],
             "conversation": j["conversation"], "stopping": j["stop"].is_set()}
            for k, j in sorted(_jobs.items(), key=lambda kj: kj[1]["queued"]) if j["status"] in ACTIVE
        ]


def remove(job_id: str) -> bool:
    """Stop a question. False if it isn't waiting or being answered."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None or job["status"] not in ACTIVE:
            return False
        job["stop"].set()
        if job["status"] == "waiting":
            job.update(status="stopped", message="Taken out of the queue.")
    return True


def _update(job_id: str, **changes):
    with _lock:
        _jobs[job_id].update(changes)


def _next_job() -> str:
    """Wait for the next question. If none comes for a while, let go of the model first, then keep waiting."""
    try:
        return _queue.get(timeout=max(settings.get()["unload_after_minutes"] * 60, 1))
    except queue_module.Empty:
        models.unload()
        return _queue.get()


def _work():
    while True:
        job_id = _next_job()
        job = _jobs[job_id]
        if job["status"] != "waiting":  # stopped while it waited
            continue
        try:
            with tools.scoped(job["folders"]):
                _answer(job_id, job)
        except Exception as err:  # shown to the user; the full error goes to the console
            traceback.print_exc()
            text = str(err).splitlines()[0] if str(err) else type(err).__name__
            _update(job_id, status="failed", message=text)
            _save_answer(job, "failed", text)
        _forget_old()


def _answer(job_id: str, job: dict):
    models.ensure(job["model"], on_stage=lambda stage: _update(job_id, status=stage))
    if job["stop"].is_set():
        _update(job_id, status="stopped", message="Stopped before it started.")
        return
    m = settings.model(job["model"]) or {}
    template = settings.template(m, job["thinking_level"])
    budget = settings.budget(m, job["thinking_level"])
    thought = 0  # thinking tokens so far, for the budget
    instructions = tools.instructions(job["can_edit"], job.get("work_folder", ""), job.get("can_run", False))
    has_editor = bool(job["conversation"]) and job["source"] == "you"
    if has_editor:
        instructions += ("\nUse open_editor when the user asks to open or show a file for live editing. "
                         "It shows one file at a time. Read it separately before making changes.")
        if job["editor_path"]:
            instructions += f"\nThe user has this file open in the editor: {json.dumps(job['editor_path'])}."
    messages = [{"role": "system", "content": instructions}]
    messages += job["messages"] if job["messages"] is not None else _conversation(job["conversation"])
    definitions = tools.DEFINITIONS + (tools.EDIT_DEFINITIONS if job["can_edit"] else [])
    if has_editor:
        definitions = definitions + [tools.EDITOR_DEFINITION]
    if checks.for_folder(job.get("work_folder", "")):
        definitions = definitions + [tools.CHECK_DEFINITION]
    if job.get("can_run"):
        definitions = definitions + [tools.COMMAND_DEFINITION]
    _update(job_id, status="thinking")
    started = time.time()
    count = 0
    writing = 0.0  # seconds spent writing (not loading, not running tools), for the speed
    finish = "stop"
    most = job.get("max_steps") or settings.get()["max_steps"]  # a bulk task can allow fewer
    for step in range(most + 1):
        last = step == most
        calls, said, first, latest = [], "", 0.0, 0.0
        # the last step has no tools, so it must answer with what it found
        cut = (lambda: thought >= budget) if budget else (lambda: False)
        for kind, piece in models.stream(messages, template, job["stop"], None if last else definitions, cut):
            if kind == "finish":
                finish = piece
                break
            now = time.time()
            first = first or now
            latest = now
            if kind == "tool":
                calls.append(piece)
                continue
            count += 1
            with _lock:
                if kind == "thinking":
                    job["thinking"] += piece
                    thought += 1
                else:
                    said += piece
                    job["answer"] += piece
                    job["status"] = "answering"
                job["tokens"] = count
                job["seconds"] = round(now - started, 1)
                job["per_second"] = round(count / (writing + now - first), 1) if writing + now - first > 0 else 0
        writing += latest - first
        if finish == "budget":
            # its thinking budget is used up: no more thinking for this question; it answers from its notes
            budget = 0
            template = settings.template(m, "off")
            messages.append({"role": "user", "content": (
                "(Time's up for thinking. Your thinking so far, as notes:)\n\n" + job["thinking"].strip() +
                "\n\n(Now give your answer to the question above, using these notes. Don't think any more.)")})
            _update(job_id, status="answering",
                     message=f"Thinking stopped at its budget ({thought:,} tokens); it answered from its notes.")
            finish = "stop"
            continue
        if finish == "stopped" or not calls:
            break
        # it wants to look at something: what it said before (if anything) was it thinking out loud
        with _lock:
            if said:
                job["answer"] = job["answer"][: len(job["answer"]) - len(said)]
                job["thinking"] += ("\n" if job["thinking"] else "") + said
            job["status"] = "looking"
        messages.append({"role": "assistant", "content": said, "tool_calls": calls})
        for call in calls:
            name = call["function"]["name"]
            arguments = call["function"].get("arguments") or "{}"
            result, summary, ok = tools.run(
                name, arguments, job["changes"], job.get("can_run", False),
                open_editor=(lambda path: _update(job_id, editor_path=path)) if has_editor else None,
            )
            if not ok and any(s["tool"] == name and s["arguments"] == _short(arguments) and not s["ok"] for s in job["steps"]):
                # the same call failed before: say so plainly, or a small model can try it again and again
                result += " (You tried exactly this before and it failed the same way: do something different.)"
            with _lock:
                job["steps"].append({"tool": name, "arguments": _short(arguments), "summary": summary, "ok": ok})
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "name": name, "content": result})
        _update(job_id, status="thinking")
    if finish == "stopped":
        _update(job_id, status="stopped", message="Stopped. What it wrote so far is kept.")
        _save_answer(job, "stopped")
    else:
        if finish == "length":
            _update(job_id, message="It ran out of room (the longest answer is max_tokens in settings.json).")
        _update(job_id, status="done")
        _save_answer(job, "done")


def _conversation(conv_id: str) -> list[dict]:
    """The conversation so far as questions and answers (not the files looked at on the way: it can look again),
    leaving out questions that got no answer (failed, or stopped before a word), so it goes question, answer..."""
    messages = []
    for m in history.get(conv_id)["messages"]:
        if m["role"] == "assistant" and (m.get("status") == "failed" or not m["content"]):
            if messages and messages[-1]["role"] == "user":
                messages.pop()
            continue
        if m["role"] == "user" and messages and messages[-1]["role"] == "user":
            messages.pop()  # a question left with no answer at all (the server stopped mid-answer)
        messages.append({"role": m["role"], "content": m["content"]})
    return messages


def _short(arguments: str) -> dict:
    """A tool call's arguments, for the page."""
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
        return {k: (v if len(str(v)) <= 200 else str(v)[:197] + "...") for k, v in args.items()}
    except (ValueError, TypeError):
        return {"raw": str(arguments)[:200]}


def _save_answer(job: dict, status: str, error: str = ""):
    m = settings.model(job["model"]) or {}
    if job["on_done"]:  # a bulk item: its run keeps the result
        try:
            job["on_done"](job, status, error)
        except Exception:
            traceback.print_exc()
        return
    history.add(job["conversation"], {
        "role": "assistant", "content": job["answer"] or error, "thinking": job["thinking"], "status": status,
        "steps": job["steps"], "thinking_level": job["thinking_level"], "can_edit": job["can_edit"],
        "changes": job["changes"].summary() if job["changes"] else [],
        "model": job["model"], "model_name": m.get("name", job["model"]), "seconds": job["seconds"],
        "tokens": job["tokens"], "per_second": job["per_second"], "time": time.time(),
    })


def _forget_old():
    with _lock:
        finished = [k for k, j in _jobs.items() if j["status"] not in ACTIVE]
        for key in finished[:-KEEP]:
            del _jobs[key]
