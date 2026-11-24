"""CodeAi's MCP connector: lets Claude (or Codex, or any MCP client) send questions to the local models.

It's a small program the client starts itself and talks to over stdin/stdout (MCP's "stdio" kind), and all it does
is call CodeAi's own API (http://localhost:8200, or CODEAI_URL). So CodeAi has to be running; Claude's questions go
in the same queue as yours, show "Claude asked" on the page, and are kept in History.

Hand-rolled on purpose (no packages to install): MCP over stdio is JSON-RPC 2.0, one message per line.

    Tools: codeai_ask, codeai_result, codeai_queue, codeai_stop, codeai_models, codeai_history,
           codeai_bulk_start, codeai_bulk_status, codeai_bulk_stop
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("CODEAI_URL", "http://localhost:8200").rstrip("/")
PROTOCOL = "2025-06-18"
DONE = ("done", "stopped", "failed")
MAX_WAIT = 600  # longest one codeai_result call waits for an answer, in seconds


class ApiError(Exception):
    pass


def api(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data, {"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        try:
            detail = json.load(err).get("detail")
        except ValueError:
            detail = None
        raise ApiError(detail or f"CodeAi answered {err.code}.")
    except (urllib.error.URLError, OSError):
        raise ApiError(f"CodeAi isn't running at {BASE}. Ask the user to start it: python3 start.py in the Code-Ai folder.")


# ---------- what Claude sees ----------

def describe_job(job_id: str, j: dict) -> str:
    """A job's state as text for Claude: the answer when it's done, else where it's got to."""
    status = j["status"]
    lines = [f"job: {job_id}", f"conversation: {j['conversation']}", f"model: {j['model']}", f"status: {status}"]
    if j.get("steps"):
        lines.append("looked at: " + "; ".join(f"{s['tool']} {json.dumps(s['arguments'])} -> {s['summary']}" for s in j["steps"]))
    if j.get("changes"):
        lines.append("changed files: " + ", ".join(f["path"] + ("" if f["existed"] else " (new)") for f in j["changes"])
                     + "  (backed up; the user can Undo them on the CodeAi page)")
    if status == "waiting":
        lines.append(f"{j.get('ahead', 0)} question(s) ahead of it in the queue.")
    if status in DONE:
        lines.append(f"took {j['seconds']} s at {j['per_second']} tokens/s")
        if j.get("message"):
            lines.append(j["message"])
        lines.append("\nanswer:\n" + (j["answer"] or "(no answer)"))
    else:
        lines.append(f"\nNot finished: call codeai_result with job {job_id} again (written so far: {len(j['answer'])} characters).")
    return "\n".join(lines)


def wait_for(job_id: str, seconds: float) -> str:
    deadline = time.time() + min(max(seconds, 0), MAX_WAIT)
    while True:
        j = api("GET", f"/api/jobs/{job_id}")
        if j["status"] in DONE or time.time() >= deadline:
            return describe_job(job_id, j)
        time.sleep(1)


def ask(prompt: str, model: str = "", thinking: str = "", conversation: str = "", wait_seconds: float = 0,
        can_change_files: bool = False) -> str:
    started = api("POST", "/api/ask", {"prompt": prompt, "model": model, "thinking": thinking,
                                       "conversation": conversation, "source": "claude",
                                       "can_edit": bool(can_change_files)})
    if wait_seconds:
        return wait_for(started["job"], wait_seconds)
    return (f"Queued. job: {started['job']}\nconversation: {started['conversation']}\n"
            "Get the answer with codeai_result (it can wait for it). Ask follow-ups with this conversation id.")


def result(job: str, wait_seconds: float = 120) -> str:
    return wait_for(job, wait_seconds)


def queue() -> str:
    jobs = api("GET", "/api/queue")
    if not jobs:
        return "The queue is empty."
    return "\n".join(f"{j['id']}  {j['status']}  {j['model']}  asked by {j['source']}: {j['prompt'][:100]}" for j in jobs)


def stop(job: str) -> str:
    api("DELETE", f"/api/queue/{job}")
    return f"Stopped {job}. What it wrote so far is kept."


def models() -> str:
    data = api("GET", "/api/models")
    lines = []
    for m in data["models"]:
        levels = ", ".join(t["id"] for t in m["thinking"]) or "none"
        lines.append(f"{m['id']}: {m['name']} ({m['note']}) thinking: {levels}" + ("  [default]" if m["id"] == data["default"] else ""))
    lines.append("\nFolders the models can read: " + ", ".join(f["path"] for f in data.get("folders", [])))
    return "\n".join(lines)


def history(conversation: str = "") -> str:
    if not conversation:
        convs = api("GET", "/api/history")[:30]
        return "\n".join(f"{c['id']}  {c['model']}  {c['questions']} question(s): {c['title']}" for c in convs) or "No conversations yet."
    conv = api("GET", f"/api/history/{conversation}")
    parts = [f"# {conv['title']}"]
    for m in conv["messages"]:
        who = ("Claude" if m.get("from") == "claude" else "User") if m["role"] == "user" else m.get("model_name", "Model")
        parts.append(f"\n## {who}\n{m['content']}")
    return "\n".join(parts)


def bulk_start(file, folder: str = "", model: str = "", thinking: str = "", can_change_files: bool | None = None,
               name: str = "") -> str:
    if isinstance(file, str):  # a path to a bulk file on this Mac
        path = Path(file).expanduser()
        try:
            file = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            raise ApiError(f"Can't read the bulk file {path}: {err}")
    run = api("POST", "/api/bulk", {"file": file, "folder": folder, "model": model, "thinking": thinking,
                                    "can_change_files": can_change_files, "name": name, "source": "claude"})
    return (f"Started bulk run {run['id']}: {run['name']}, {run['total']} items, in {run['folder']}.\n"
            "Each item is asked on its own with a fresh memory. Follow it with codeai_bulk_status; the user can watch "
            f"it on the CodeAi page (Bulk tab, {BASE}/#bulk/{run['id']}).")


def bulk_status(run: str = "", wait_seconds: float = 0, show: str = "problems") -> str:
    if not run:
        runs = api("GET", "/api/bulk")
        listing = "\n".join(f"{r['id']}  {r['status']}  {r['name']}  {json.dumps(r['counts'])}" for r in runs[:20])
        return f"Runs (newest first):\n{listing or '(none yet)'}"
    deadline = time.time() + min(max(wait_seconds, 0), MAX_WAIT)
    while True:
        r = api("GET", f"/api/bulk/{run}")
        if r["status"] not in ("running", "stopping") or time.time() >= deadline:
            break
        time.sleep(3)
    counts = {}
    for i in r["items"]:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
    lines = [f"run {r['id']}: {r['name']}", f"status: {r['status']}", f"items: {json.dumps(counts)} of {len(r['items'])}",
             f"time so far: {round(r['seconds'])} s"]
    picked = [i for i in r["items"] if show == "all" or (show == "problems" and i["status"] in
                                                          ("failed", "unchanged", "error", "stopped"))
              or (show == "problems" and (i.get("review") or "").startswith(("No PASS", "Not reviewed")))]
    for i in picked[:100]:
        lines.append(f"\n#{i['n']} {i['status']}: {json.dumps(i['fields'])}\n  check: {i['check']}\n  review: {i.get('review', '')}\n  model said: "
                     + (i["answer"] or "").strip().replace("\n", " ")[:400])
    return "\n".join(lines)


def bulk_stop(run: str) -> str:
    r = api("POST", f"/api/bulk/{run}/stop")
    return f"Run {run} is {r['status']}. Done items stay done; Carry on (on the page) picks it up again."


S = {"type": "string"}
TOOLS = [
    {"name": "codeai_ask", "function": ask,
     "description": "Send a question or coding task to a local model on the user's Mac (CodeAi: Gemma 4 31B by default, "
                    "about 15 tokens/s). It can read files in the user's Desktop, Documents and Downloads, and with "
                    "can_change_files it can also make and change files there (each backed up first). Returns a job id at once (or waits up to wait_seconds for the answer); then use "
                    "codeai_result. Good for bulk or routine work you'd like done locally; check what comes back.",
     "inputSchema": {"type": "object", "required": ["prompt"], "properties": {
         "prompt": {**S, "description": "The question or task, written as a clear, complete brief."},
         "model": {**S, "description": "A model id from codeai_models; empty = the default."},
         "thinking": {**S, "description": "on / off (Gemma, Qwen); empty = the model's default (on)."},
         "conversation": {**S, "description": "A conversation id to ask a follow-up in; empty = a new conversation."},
         "wait_seconds": {"type": "number", "description": "Wait this long (up to 600) for the answer; 0 = don't wait."},
         "can_change_files": {"type": "boolean", "description": "Let it make and change files (off unless the user "
                              "wants changes made). Review its changes afterwards."}}}},
    {"name": "codeai_result", "function": result,
     "description": "A CodeAi job's answer, or how far it's got. Waits up to wait_seconds (default 120, most 600) for it to finish.",
     "inputSchema": {"type": "object", "required": ["job"], "properties": {
         "job": S, "wait_seconds": {"type": "number"}}}},
    {"name": "codeai_queue", "function": queue,
     "description": "The questions waiting or being answered in CodeAi, in order.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "codeai_stop", "function": stop,
     "description": "Stop a CodeAi job (a waiting one is dropped; one being answered stops where it is).",
     "inputSchema": {"type": "object", "required": ["job"], "properties": {"job": S}}},
    {"name": "codeai_models", "function": models,
     "description": "The local models CodeAi has (ids, notes, thinking choices) and the folders they can read.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "codeai_bulk_start", "function": bulk_start,
     "description": "Start a bulk run in CodeAi: one prompt done over a list of items by a local model, each item asked "
                    "on its own with a fresh memory, one at a time (the user's own questions slip in between items). "
                    "Everything about the job is in the bulk file, a JSON object: prompt (one string or a list of "
                    "lines, {field} for an item's parts, {folder} for the folder), items (a list of objects, each "
                    "with every field it needs, e.g. {\"character\": \"Becky\", \"old\": ..., \"new\": ...}), "
                    "and optionally name, model, thinking, can_change_files (default true), required (fields "
                    "every item needs), search (text "
                    "CodeAi finds in the folder first, e.g. \"{old}\"), checks (CodeAi's own tests of each change: "
                    "changed; lines {most, in_place}; had/has {text, share}: a changed line held / now has the text; lacks {pattern}: no changed line matches it; "
                    "kept {pattern, about}: what the regex matches stays the same), review (a second prompt that "
                    "looks at the change and says PASS or FAIL), retries, max_steps. A failed check or review undoes "
                    "the item and retries it. Examples: the examples/ folder in CodeAi. Every change is backed up; "
                    "the user can undo an item or the whole run on the Bulk tab.",
     "inputSchema": {"type": "object", "required": ["file"], "properties": {
         "file": {"description": "The bulk file: the JSON object, or the path of a .json file on this Mac."},
         "folder": {**S, "description": "The one folder it may look in (inside the allowed folders)."},
         "model": {**S, "description": "Empty = the file's, or the default."},
         "thinking": {**S, "description": "on / short / off ...; empty = the file's."},
         "can_change_files": {"type": "boolean", "description": "Empty = the file's (on if it doesn't say)."},
         "name": S}}},
    {"name": "codeai_bulk_status", "function": bulk_status,
     "description": "A bulk run's progress and its problem items (or with no run: the recent runs). "
                    "wait_seconds (up to 600) waits for it to finish first. show: problems (default), all or none.",
     "inputSchema": {"type": "object", "properties": {"run": S, "wait_seconds": {"type": "number"},
                                                      "show": {**S, "enum": ["problems", "all", "none"]}}}},
    {"name": "codeai_bulk_stop", "function": bulk_stop,
     "description": "Stop a bulk run (the item being worked on stops; the rest wait for Carry on).",
     "inputSchema": {"type": "object", "required": ["run"], "properties": {"run": S}}},
    {"name": "codeai_history", "function": history,
     "description": "Past CodeAi conversations (newest first), or one in full when given its id.",
     "inputSchema": {"type": "object", "properties": {"conversation": S}}},
]
BY_NAME = {t["name"]: t for t in TOOLS}


# ---------- MCP over stdio (JSON-RPC 2.0, one message per line) ----------

def reply(msg_id, result=None, error=None):
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error:
        out["error"] = error
    else:
        out["result"] = result
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


def handle(msg: dict):
    method, msg_id, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if msg_id is None:
        return  # a notification (e.g. notifications/initialized): nothing to answer
    if method == "initialize":
        return reply(msg_id, {
            "protocolVersion": params.get("protocolVersion", PROTOCOL),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "codeai", "version": "1.0"},
            "instructions": "CodeAi runs local AI models on the user's Mac. Use codeai_ask to hand it work, then "
                            "codeai_result to collect the answer. It's slower than you and can be wrong: review "
                            "what comes back before using it.",
        })
    if method == "ping":
        return reply(msg_id, {})
    if method == "tools/list":
        return reply(msg_id, {"tools": [{k: v for k, v in t.items() if k != "function"} for t in TOOLS]})
    if method == "tools/call":
        tool = BY_NAME.get(params.get("name"))
        if tool is None:
            return reply(msg_id, error={"code": -32602, "message": f"No tool called {params.get('name')}."})
        try:
            text = tool["function"](**(params.get("arguments") or {}))
            return reply(msg_id, {"content": [{"type": "text", "text": text}]})
        except ApiError as err:
            return reply(msg_id, {"content": [{"type": "text", "text": str(err)}], "isError": True})
        except TypeError as err:
            return reply(msg_id, {"content": [{"type": "text", "text": f"Wrong arguments: {err}"}], "isError": True})
    reply(msg_id, error={"code": -32601, "message": f"Unknown method {method}."})


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply(None, error={"code": -32700, "message": "Not JSON."})
            continue
        try:
            handle(msg)
        except Exception as err:  # never die on one bad call
            reply(msg.get("id"), error={"code": -32603, "message": str(err)})


if __name__ == "__main__":
    main()
