"""Bulk jobs: one job done over a long list of items (change these 300 lines of dialogue, summarise these files, ...).

Everything about the job is in the bulk file you give, none of it in CodeAi's code, so a new kind of bulk job is a new
file, never a code change:

    {
      "name": "shown in the runs list",
      "prompt": "the instructions for ONE item, with {field} for each of its parts ({folder} = the run's folder)",
      "items": [{"field": "value", ...}, ...],
      "folder": "...", "model": "...", "thinking": "...", "can_change_files": true (the default),
      "required": ["fields every item must have"],
      "search": "text CodeAi looks for in the folder first ({field}s fine), so the model starts at the right lines",
      "checks": [CodeAi's own tests of what an item changed (CHECKS below)],
      "review": "a second prompt: a fresh question that looks at the change and answers PASS or FAIL",
      "retries": 1 (the default), "max_steps": 12 (the default)
    }

A prompt can be one string or a list of lines. Each item is its own question, asked with a fresh memory: the model
sees only the prompt filled in with that one item, never the items before it. That keeps every item as quick and as
careful as the first, however long the list, and a mistake in one can't spill into the next.

Items go into the queue one at a time, so a question asked on the Ask tab waits for one item at most, not the whole
run. When an item changed files, its checks run, then its review: if either says it's wrong, CodeAi undoes it and
tries once more with the reason; if it's still wrong, it's undone and marked for you.

Runs are kept in bulk/<id>.json (git-ignored), saved after every item, so a restart loses nothing: a run that was
going when CodeAi stopped shows as paused, and Carry on picks it up at the next item.
"""

import json
import re
import threading
import time
import uuid
from pathlib import Path

from . import jobs, settings, tools

_lock = threading.RLock()
_runs: dict[str, dict] = {}
NOT_GIVEN = "(not given)"
MAX_ITEMS = 5000
BULK_MAX_STEPS = 12  # tool uses per item unless the file says: an item is a small job, so one it can't find stops soon
FIELD = re.compile(r"\{(\w+)\}")


class BulkError(Exception):
    pass


# ---------- the bulk file ----------

def _text(value) -> str:
    """A prompt: one string, or a list of lines (easier to write in JSON)."""
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return str(value or "")


def read_items(data) -> list[dict]:
    """The items: a list of objects, each one item's fields: [{"character": "Becky", "old": "...", "new": "..."}, ...]."""
    if not isinstance(data, list):
        raise BulkError("\"items\" should be a list: [{\"old\": \"...\", \"new\": \"...\"}, ...].")
    for item in data:
        if not isinstance(item, dict):
            raise BulkError("Each item should be an object, like {\"old\": \"...\", \"new\": \"...\"}.")
    if len(data) > MAX_ITEMS:
        raise BulkError(f"That's {len(data):,} items; {MAX_ITEMS:,} at most in one run.")
    return [{k: v if isinstance(v, str) else json.dumps(v) for k, v in i.items()} for i in data]


def _fill(template: str, fields: dict) -> str:
    return FIELD.sub(lambda m: str(fields.get(m.group(1)) or NOT_GIVEN), template)


def _fill_or_skip(template: str, fields: dict) -> str | None:
    """The template filled in, or None when it uses a field this item doesn't have (that check is skipped)."""
    if any(not str(fields.get(f) or "").strip() for f in FIELD.findall(template)):
        return None
    return FIELD.sub(lambda m: str(fields[m.group(1)]), template)


def _hint(search: str) -> str:
    """Where the search text already is in the folder, so the model starts there."""
    text = search.strip()
    if len(text) < 3:
        return ""
    # look for a distinctive middle part, so small differences at the ends (a full stop, a quote) don't hide it
    words = re.findall(r"[\w']+", text)
    probe = max((" ".join(words[i:i + 4]) for i in range(max(len(words) - 3, 1))), key=len) if words else text
    pattern = r"\W+".join(re.escape(w) for w in probe.split())
    found, _ = tools.search(pattern, "")
    if found.startswith("No lines match"):
        return f"(CodeAi looked for \"{text}\" and found nothing with those words: search for other parts of it.)"
    lines = found.splitlines()
    more = f"\n(and {len(lines) - 15} more)" if len(lines) > 15 else ""
    return f"CodeAi found these lines with words from \"{text}\" (file:line: text):\n" + "\n".join(lines[:15]) + more


# ---------- checks: CodeAi looks at what an item changed ----------
# Each check is {"type": ..., ...} in the file's "checks". Text in a check can use {field}s; a check whose text needs
# a field the item doesn't have is skipped. Text is compared loosely: case, curly quotes, \-escapes and spacing
# don't matter. "share" (0 to 1, optional) asks only for that share of the text's words (longer than 3 letters, the
# same word give or take an ending, so crash/crashed and twin/twins match) instead of all of it as written.

def _loose(text: str) -> str:
    text = re.sub(r"\\(.)", r"\1", text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def _share(wanted: str, text: str) -> float:
    keys = [w for w in re.findall(r"[a-z0-9']+", _loose(wanted)) if len(w) > 3]
    if not keys:
        return 1.0
    have = re.findall(r"[a-z0-9']+", _loose(text))
    return sum(any(_same_word(h, w) for h in have) for w in keys) / len(keys)


def _same_word(a: str, b: str) -> bool:
    """The same word give or take an ending: crash/crashed, twin/twins, dinosaur/dinosaurs."""
    n = min(len(a), len(b), 5)
    return n >= 4 and a[:n] == b[:n]


def _holds(line: str, text: str, share) -> bool:
    if share is None:
        return _loose(text) in _loose(line)
    return _share(text, line) >= float(share)


def _lines(changes: list[dict]) -> tuple[list[str], list[str], list[tuple]]:
    """The lines an item took out, put in, and (file, before, after) pairs when each file's were changed one for one."""
    removed, added, pairs = [], [], []
    for f in changes:
        diff = f.get("diff", "").splitlines()  # its --- and +++ header lines are already gone
        out = [l[1:] for l in diff if l.startswith("-")]
        put = [l[1:] for l in diff if l.startswith("+")]
        removed += out
        added += put
        if len(out) == len(put):
            pairs += [(Path(f["path"]).name, a, b) for a, b in zip(out, put)]
        else:
            pairs.append((Path(f["path"]).name, None, None))
    return removed, added, pairs


def check_changed(spec, fields, changes):
    """{"type": "changed"}: it changed at least one file."""
    return (True, "") if changes else (False, "Nothing was changed.")


def check_lines(spec, fields, changes):
    """{"type": "lines", "most": 3, "in_place": true}: at most this many lines changed; in_place: each line changed
    where it is (one line out, one in), none added or taken away."""
    removed, added, pairs = _lines(changes)
    if spec.get("in_place") and any(b is None for _, b, _ in pairs):
        name = next(n for n, b, _ in pairs if b is None)
        return False, f"{name}: lines were added or taken out; change the lines in place, one for one."
    most = spec.get("most")
    if most is not None and max(len(removed), len(added)) > int(most):
        return False, f"{max(len(removed), len(added))} lines were changed; this should change {most} at most."
    return True, ""


def check_had(spec, fields, changes):
    """{"type": "had", "text": "{old}", "share": 0.6}: a line it changed held this text before (so it changed the
    right one)."""
    text = _fill_or_skip(_text(spec.get("text")), fields)
    if text is None:
        return True, ""
    removed, _, _ = _lines(changes)
    if any(_holds(l, text, spec.get("share")) for l in removed):
        return True, ""
    shown = "; ".join(f'"{l.strip()}"' for l in removed[:3])
    return False, f"The line(s) it changed ({shown}) didn't hold \"{text}\"."


def check_has(spec, fields, changes):
    """{"type": "has", "text": "{new}", "share": 0.6}: a line it changed has this text now."""
    text = _fill_or_skip(_text(spec.get("text")), fields)
    if text is None:
        return True, ""
    _, added, _ = _lines(changes)
    if any(_holds(l, text, spec.get("share")) for l in added):
        return True, ""
    shown = "; ".join(f'"{l.strip()}"' for l in added[:3])
    return False, f"The changed line(s) now say {shown or 'nothing'}, which leaves out \"{text}\"."


def check_kept(spec, fields, changes):
    """{"type": "kept", "pattern": "regex", "about": "the speaker's name"}: in each changed line, what the pattern
    matches is the same before and after (an indent, a name, #tags at the end...)."""
    pattern = _fill_or_skip(_text(spec.get("pattern")), fields)
    if pattern is None:
        return True, ""
    try:
        rx = re.compile(pattern)
    except re.error as err:
        return False, f"The file's \"kept\" pattern is broken ({err})."
    about = spec.get("about") or f"the part matching {pattern}"
    for name, before, after in _lines(changes)[2]:
        if before is None:
            return False, f"{name}: lines were added or taken out, so CodeAi can't tell if {about} was kept."
        b, a = rx.search(before), rx.search(after)
        if (b.group(0) if b else None) != (a.group(0) if a else None):
            return False, f"{name}: {about} changed (\"{b.group(0) if b else ''}\" to \"{a.group(0) if a else ''}\"); keep it as it was."
    return True, ""


def check_lacks(spec, fields, changes):
    """{"type": "lacks", "pattern": "regex", "about": "a # that isn't written \\#"}: no line it changed matches the
    pattern now (something that must never be in a changed line)."""
    pattern = _fill_or_skip(_text(spec.get("pattern")), fields)
    if pattern is None:
        return True, ""
    try:
        rx = re.compile(pattern)
    except re.error as err:
        return False, f"The file's \"lacks\" pattern is broken ({err})."
    about = spec.get("about") or f"something matching {pattern}"
    for line in _lines(changes)[1]:
        if rx.search(line):
            return False, f"\"{line.strip()}\" has {about}; fix that."
    return True, ""


CHECKS = {"changed": check_changed, "lines": check_lines, "had": check_had, "has": check_has, "kept": check_kept,
          "lacks": check_lacks}


def _check(checks: list, fields: dict, changes: list) -> tuple[bool, str]:
    for spec in checks:
        ok, why = CHECKS[spec["type"]](spec, fields, changes)
        if not ok:
            return False, why
    where = ", ".join(sorted({Path(f["path"]).name for f in changes}))
    _, added, _ = _lines(changes)
    now = f" Now: \"{added[0].strip()}\"" if len(added) == 1 else ""
    return True, f"Changed {where}.{now}"


def _read_file(file: dict) -> dict:
    """Check a bulk file and work out its settings (everything but folder, model and the items)."""
    if not isinstance(file, dict):
        raise BulkError("A bulk file is a JSON object: {\"prompt\": \"...\", \"items\": [...]}.")
    prompt = _text(file.get("prompt")).strip()
    if not prompt:
        raise BulkError("The file needs a \"prompt\": the instructions for one item, with {field} for its parts.")
    if "items" not in file:
        raise BulkError("The file needs \"items\": the list of things to do.")
    checks = file.get("checks") or []
    if not isinstance(checks, list) or not all(isinstance(c, dict) for c in checks):
        raise BulkError("\"checks\" should be a list like [{\"type\": \"changed\"}].")
    for c in checks:
        if c.get("type") not in CHECKS:
            raise BulkError(f"There's no check called \"{c.get('type')}\". The checks: {', '.join(CHECKS)}.")
    required = file.get("required") or []
    if isinstance(required, str):
        required = [required]
    return {"prompt": prompt, "search": _text(file.get("search")), "checks": checks,
            "review": _text(file.get("review")).strip(), "required": required,
            "retries": int(file.get("retries", 1)), "max_steps": int(file.get("max_steps", BULK_MAX_STEPS))}


# ---------- runs ----------

def _path(run_id: str) -> Path:
    return settings.folder("bulk_dir") / f"{run_id}.json"


def _save(run: dict):
    path = _path(run["id"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(run, indent=1), encoding="utf-8")
    tmp.replace(path)


def _load_all():
    """Read the saved runs once. One that was going when CodeAi stopped is paused (Carry on picks it up)."""
    if _runs.get("_loaded"):
        return
    for p in settings.folder("bulk_dir").glob("*.json"):
        try:
            run = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if run["status"] in ("running", "stopping"):
            run["status"] = "paused"
            for item in run["items"]:
                if item["status"] == "working":
                    item["status"] = "waiting"
                elif item["status"] == "reviewing":
                    item.update(status="done", review="Not reviewed (CodeAi stopped).")
            _save(run)
        _runs[run["id"]] = run
    _runs["_loaded"] = True


def _counts(run: dict) -> dict:
    counts = {}
    for item in run["items"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return counts


def summary(run: dict) -> dict:
    keys = ("id", "name", "model", "folder", "status", "created", "finished", "thinking", "can_edit", "seconds",
            "current", "job")
    out = {k: run.get(k) for k in keys}
    out["total"] = len(run["items"])
    out["counts"] = _counts(run)
    return out


def listing() -> list[dict]:
    with _lock:
        _load_all()
        runs = [r for k, r in _runs.items() if k != "_loaded"]
        return [summary(r) for r in sorted(runs, key=lambda r: r["created"], reverse=True)]


def get(run_id: str) -> dict | None:
    with _lock:
        _load_all()
        run = _runs.get(run_id)
        return json.loads(json.dumps(run)) if run else None


def start(file: dict, folder: str = "", model_id: str = "", thinking: str = "", can_edit: bool | None = None,
          name: str = "", source: str = "you") -> dict:
    """Start a run from a bulk file. folder, model, thinking and can_edit, when given, win over the file's; name is
    used when the file has none (the page sends the file's own name: becky-fixes.json -> becky-fixes)."""
    with _lock:
        _load_all()
    spec = _read_file(file)
    items = read_items(file["items"])
    if not items:
        raise BulkError("There are no items in it.")
    for n, item in enumerate(items, 1):
        missing = [f for f in spec["required"] if not str(item.get(f, "")).strip()]
        if missing:
            raise BulkError(f"Item {n} has no {' or '.join(missing)}.")
    folder = folder or str(file.get("folder") or "")
    where = tools.inside_allowed(folder)
    if where is None:
        allowed = ", ".join(f["path"] for f in tools.folders())
        raise BulkError(f"Pick a folder inside the allowed ones ({allowed}).")
    model_id = model_id or str(file.get("model") or "") or (settings.models() or [{}])[0].get("id")
    if not model_id or settings.model(model_id) is None:
        raise BulkError(f"There's no model called {model_id} on this computer.")
    if can_edit is None:
        can_edit = bool(file.get("can_change_files", True))
    run = {
        "id": uuid.uuid4().hex[:12], "name": str(file.get("name") or "").strip() or name.strip() or f"Bulk run ({len(items)})",
        **spec, "model": model_id, "folder": str(where), "thinking": thinking or str(file.get("thinking") or ""),
        "can_edit": can_edit, "source": source, "status": "running", "created": time.time(), "finished": None,
        "seconds": 0, "current": None, "job": None,
        "items": [{"n": n, "fields": item, "status": "waiting", "tries": 0, "answer": "", "thinking": "",
                   "steps": [], "changes": [], "check": "", "review": "", "seconds": 0, "tokens": 0, "undone": False}
                  for n, item in enumerate(items, 1)],
    }
    with _lock:
        _runs[run["id"]] = run
        _save(run)
        _next(run)
    return summary(run)


def _fields(run: dict, item: dict) -> dict:
    return {**item["fields"], "folder": run["folder"]}


def _messages(run: dict, item: dict, retry_reason: str = "") -> list[dict]:
    fields = _fields(run, item)
    text = _fill(run["prompt"], fields)
    search = _fill_or_skip(run.get("search", ""), fields) if run.get("search") else None
    if search:
        with tools.scoped([run["folder"]]):
            hint = _hint(search)
        if hint:
            text += "\n\n" + hint
    if retry_reason:
        text += ("\n\nA try at this item was undone, because CodeAi's check found: " + retry_reason +
                 "\nThe files are back as they were. Try again, fixing that.")
    return [{"role": "user", "content": text}]


def _review_messages(run: dict, item: dict) -> list[dict]:
    diffs = "\n\n".join(f"{f['path']}:\n```diff\n{f.get('diff', '')}\n```" for f in item["changes"])
    fields = {**_fields(run, item), "changes": diffs, "answer": item["answer"]}
    text = _fill(run["review"], fields)
    if "{changes}" not in run["review"]:
        text += "\n\nWhat was changed:\n" + diffs
    text += ("\n\nDon't change any files. Start your answer with PASS if the change is right, or FAIL and one line "
             "saying what's wrong.")
    return [{"role": "user", "content": text}]


def _submit(run: dict, item: dict, messages: list[dict], can_edit: bool, what: str):
    run["job"] = jobs.submit(None, run["model"], f"Bulk: {run['name']}, item {item['n']}{what}", run["source"],
                             run["thinking"], can_edit, bulk={
                                 "run": run["id"], "index": item["n"], "folders": [run["folder"]],
                                 "max_steps": run.get("max_steps", 0), "messages": messages,
                                 "on_done": lambda job, status, error: _done(run["id"], item["n"], job, status, error)})


def _next(run: dict, retry_reason: str = ""):
    """Queue the next waiting item (or the same one again for a retry), or finish the run. Holds _lock."""
    if run["status"] != "running":
        return
    item = next((i for i in run["items"] if i["status"] == "waiting"), None)
    if item is None:
        run.update(status="done", finished=time.time(), current=None, job=None)
        _save(run)
        return
    item["status"] = "working"
    item["tries"] += 1
    run["current"] = item["n"]
    try:
        _submit(run, item, _messages(run, item, retry_reason), run["can_edit"], "")
    except jobs.QueueFull:
        item["status"], item["tries"] = "waiting", item["tries"] - 1
        run.update(status="paused", current=None, job=None)
    _save(run)


def _wrong(run: dict, item: dict, why: str) -> str:
    """An item's change was wrong: undo it; the reason to retry with, or '' when it's out of tries."""
    if item["changes"] and not item["undone"]:
        item["undo_notes"] = tools.undo(item["changes"])
        item["undone"] = True
    if item["tries"] <= run["retries"]:
        item["status"] = "waiting"
        return why
    item["status"] = "failed"
    return ""


def _verdict(answer: str) -> tuple[bool | None, str]:
    m = re.search(r"\b(PASS|FAIL)\b", answer or "")
    if not m:
        return None, (answer or "").strip()[:300]
    rest = answer[m.end():].strip(" :.-\n")
    return m.group(1) == "PASS", rest.splitlines()[0][:300] if rest else ""


def _done(run_id: str, n: int, job: dict, status: str, error: str):
    """An item's question (or its review) finished: check it, review it, retry it, or go on to the next."""
    with _lock:
        run = _runs[run_id]
        item = run["items"][n - 1]
        reviewing = item["status"] == "reviewing"
        item.update(seconds=round(item["seconds"] + job["seconds"], 1), tokens=item["tokens"] + job["tokens"])
        run["seconds"] = round(run["seconds"] + job["seconds"], 1)
        retry = ""
        if reviewing:
            if status != "done":
                item.update(status="done", review=f"Not reviewed ({error or status}).")
            else:
                ok, why = _verdict(job["answer"])
                item["review"] = ("PASS" if ok else "FAIL" if ok is False else "No PASS or FAIL") + (f": {why}" if why else "")
                if ok is False:
                    retry = _wrong(run, item, f"the review said: {why or 'it is wrong'}")
                else:
                    item["status"] = "done"
        else:
            changes = job["changes"].summary() if job["changes"] else []
            item.update(answer=job["answer"] or error, thinking=job["thinking"], steps=job["steps"], changes=changes,
                        undone=False, review="")
            if status == "stopped":
                item["status"] = "stopped"
            elif status == "failed":
                item.update(status="error", check=error)
            elif run["can_edit"] and run["checks"] and not changes:
                item.update(status="unchanged", check="Nothing was changed.")
            else:
                ok, why = _check(run["checks"], item["fields"], changes) if changes else (True, "")
                item["check"] = why
                if not ok:
                    retry = _wrong(run, item, why)
                elif run.get("review") and changes and run["status"] == "running":
                    item["status"] = "reviewing"
                    try:
                        _submit(run, item, _review_messages(run, item), False, " (review)")
                        _save(run)
                        return
                    except jobs.QueueFull:
                        item.update(status="done", review="Not reviewed (the queue was full).")
                else:
                    item["status"] = "done"
        if run["status"] == "stopping":
            run.update(status="stopped", current=None, job=None)
            _save(run)
            return
        _next(run, retry)
        _save(run)


def stop(run_id: str) -> dict:
    """Stop a run: the item being worked on stops too (and is marked stopped); the rest stay waiting."""
    with _lock:
        _load_all()
        run = _runs.get(run_id)
        if run is None:
            raise BulkError("That run is gone.")
        if run["status"] == "running" and run["job"] and jobs.remove(run["job"]):
            run["status"] = "stopping"
            if (jobs.status(run["job"]) or {}).get("status") == "stopped":  # it was still waiting: no answer will come
                item = run["items"][run["current"] - 1]
                if item["status"] == "reviewing":
                    item.update(status="done", review="Not reviewed (stopped).")
                else:
                    item["status"] = "stopped"
                run.update(status="stopped", current=None, job=None)
        elif run["status"] in ("running", "paused"):
            run.update(status="stopped", current=None, job=None)
        _save(run)
        return summary(run)


def carry_on(run_id: str, redo: bool = False) -> dict:
    """Start a stopped or paused run again from its next waiting item. redo: items that failed, were left unchanged
    or stopped are tried again too."""
    with _lock:
        _load_all()
        run = _runs.get(run_id)
        if run is None:
            raise BulkError("That run is gone.")
        if run["status"] in ("running", "stopping"):
            raise BulkError("It's still going.")
        again = ("stopped", "failed", "unchanged", "error") if redo else ("stopped",)
        for item in run["items"]:
            if item["status"] in again:
                item.update(status="waiting", tries=0)
        run.update(status="running", finished=None)
        _next(run)
        _save(run)
        return summary(run)


def undo_item(run_id: str, n: int) -> list[str]:
    with _lock:
        _load_all()
        run = _runs.get(run_id)
        if run is None or not 1 <= n <= len(run["items"]):
            raise BulkError("That item is gone.")
        item = run["items"][n - 1]
        if not item["changes"] or item["undone"]:
            raise BulkError("It has nothing to undo.")
        if item["status"] in ("working", "reviewing"):
            raise BulkError("It's being worked on. Stop the run first.")
        notes = tools.undo(item["changes"])
        item.update(undone=True, undo_notes=notes, status="undone")
        _save(run)
        return notes


def undo_all(run_id: str) -> dict:
    """Undo every item's changes, newest first. The run must be stopped or finished."""
    with _lock:
        _load_all()
        run = _runs.get(run_id)
        if run is None:
            raise BulkError("That run is gone.")
        if run["status"] in ("running", "stopping"):
            raise BulkError("Stop the run first.")
        undone, notes = 0, []
        for item in reversed(run["items"]):
            if item["changes"] and not item["undone"]:
                notes += tools.undo(item["changes"])
                item.update(undone=True, status="undone")
                undone += 1
        _save(run)
        return {"undone": undone, "notes": notes}


def delete(run_id: str) -> bool:
    with _lock:
        _load_all()
        run = _runs.get(run_id)
        if run is None:
            return False
        if run["status"] in ("running", "stopping"):
            raise BulkError("Stop the run first.")
        del _runs[run_id]
        _path(run_id).unlink(missing_ok=True)
        return True
