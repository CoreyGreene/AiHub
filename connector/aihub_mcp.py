"""AiHub's MCP connector: lets Claude (or any MCP client) use Image AI and 3D AI on this computer.

A small program the client starts itself and talks to over stdin/stdout (MCP's "stdio" kind). All it does is
call AiHub's own API (http://localhost:8000, or AIHUB_URL): the same queues the pages use, so the user sees
Claude's work on the pages too. A tool that isn't running is started first (through the hub), then used.

Hand-rolled on purpose (no packages to install): MCP over stdio is JSON-RPC 2.0, one message per line.
Code AI has its own connector (apps/code/connector).

    Tools: aihub_status,
           image_themes, image_make, image_job, image_workflow_run, image_workflow_status,
           image_staging, image_save_pictures, image_approve,
           mesh_make, mesh_bulk, mesh_status, mesh_models
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HUB = os.environ.get("AIHUB_URL", "http://localhost:8000").rstrip("/")
PROTOCOL = "2025-06-18"
MAX_WAIT = 600  # longest one call waits, in seconds


class ApiError(Exception):
    pass


# ---------- talking to the hub ----------

def _send(method: str, url: str, body=None, raw: bytes | None = None, timeout: float = 60):
    headers = {}
    if raw is not None:
        data = raw
    elif body is not None:
        data, headers = json.dumps(body).encode(), {"Content-Type": "application/json"}
    else:
        data = None
    request = urllib.request.Request(url, data, headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content = response.read()
        return json.loads(content) if "json" in response.headers.get("content-type", "") else content


def _start(tool: str) -> None:
    """Ask the hub to start a tool, then wait (up to 2 minutes) until it answers."""
    _send("POST", f"{HUB}/hub/api/apps/{tool}/start")
    for _ in range(120):
        time.sleep(1)
        state = next(a["state"] for a in _send("GET", f"{HUB}/hub/api/status")["apps"] if a["id"] == tool)
        if state == "running":
            return
        if state != "starting":
            raise ApiError(f"{tool} didn't start ({state}). The AI Hub page ({HUB}) shows why.")
    raise ApiError(f"{tool} took too long to start.")


def api(tool: str, method: str, path: str, body=None, raw: bytes | None = None):
    """Call a tool's own API through the hub (/<tool>/...), starting the tool if it isn't running."""
    url = f"{HUB}/{tool}/{path.lstrip('/')}"
    for attempt in (1, 2):
        try:
            return _send(method, url, body, raw)
        except urllib.error.HTTPError as err:
            if err.code == 503 and attempt == 1:
                _start(tool)
                continue
            try:
                detail = json.load(err).get("detail")
            except ValueError:
                detail = None
            raise ApiError(f"{tool}: {detail or f'answered {err.code}'}")
        except (urllib.error.URLError, OSError):
            raise ApiError(f"AI Hub isn't running at {HUB}. Ask the user to start it: python3 start.py in the Ai-Hub folder.")


def _q(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


# ---------- the hub ----------

def status() -> str:
    data = _send("GET", f"{HUB}/hub/api/status")
    lines = [f"{a['name']} ({a['id']}): {a['state']}" + (f", {a['memory'] / 1e9:.1f} GB" if a["memory"] else "")
             for a in data["apps"]]
    mac = data["mac"]
    return "\n".join(lines + [f"Mac memory: {mac['used'] / 1e9:.0f} of {mac['total'] / 1e9:.0f} GB used"])


# ---------- Image AI ----------

def image_themes() -> str:
    return "\n".join(f"{t['id']}: {t['name']} ({t.get('hint', '')})" for t in api("image", "GET", "api/themes"))


def _wait_job(job: str, seconds: float) -> dict:
    deadline = time.time() + min(seconds, MAX_WAIT)
    while True:
        j = api("image", "GET", f"api/jobs/{_q(job)}")
        if j.get("status") not in ("waiting", "working") or time.time() >= deadline:
            return j
        time.sleep(2)


def _job_text(job: str, j: dict) -> str:
    pics = ", ".join(p["picture"] for p in j.get("pictures", []))
    text = f"Job {job}: {j.get('status')}, {len(j.get('pictures', []))} of {j.get('count', '?')} pictures"
    if j.get("blocked"):
        text += f", {j['blocked']} blocked by the safety check"
    if j.get("staging"):
        text += f", in Staging as '{j['staging']}'"
    return text + (f". Picture ids: {pics}" if pics else "")


def image_make(theme: str, prompt: str, count: int = 1, wait_seconds: float = 0) -> str:
    job = api("image", "POST", "api/generate", {"theme": theme, "prompt": prompt, "count": count})["job"]
    return _job_text(job, _wait_job(job, wait_seconds)) if wait_seconds else f"Queued as job {job}."


def image_job(job: str, wait_seconds: float = 60) -> str:
    return _job_text(job, _wait_job(job, wait_seconds))


def image_workflow_run(name: str, items: list, start: bool = True) -> str:
    """Save a workflow (new, or replacing one with the same name) and start it."""
    found = next((w for w in api("image", "GET", "api/workflows") if w["name"] == name), None)
    flow = found["id"] if found else api("image", "POST", "api/workflows", {"name": name})["id"]
    api("image", "PUT", f"api/workflows/{_q(flow)}", {"name": name, "items": items})
    if start:
        api("image", "POST", f"api/workflows/{_q(flow)}/start")
    return f"Workflow '{name}' (id {flow}) saved with {len(items)} items" + (" and started." if start else ".") + \
        " Each item's pictures go to Staging under its name; follow it with image_workflow_status."


def image_workflow_status(workflow: str, wait_seconds: float = 0) -> str:
    deadline = time.time() + min(wait_seconds, MAX_WAIT)
    while True:
        flow = api("image", "GET", f"api/workflows/{_q(workflow)}")
        run = flow.get("run", [])
        if not flow.get("running") or time.time() >= deadline:
            break
        time.sleep(5)
    counts = {}
    for item in run:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    problems = [f"{i['staging']}: {i['status']}" + (f", {i['blocked']} blocked" if i.get("blocked") else "")
                for i in run if i["status"] not in ("done", "waiting", "working") or i.get("blocked")]
    text = f"{flow['name']}: {'running' if flow.get('running') else 'finished'}; " + \
        ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
    return text + ("\nProblems:\n" + "\n".join(problems) if problems else "")


def image_staging(group: str = "") -> str:
    """Without a group: every Staging group. With one: its pictures (ids)."""
    if not group:
        return "\n".join(f"{g['name']} (folder {g['folder']}): {g['count']} pictures" for g in api("image", "GET", "api/staging"))
    g = api("image", "GET", f"api/staging/{_q(group)}")
    return f"{g['name']}:\n" + "\n".join(f"{p['id']}  ({p['made']})" for p in g["pictures"])


def image_save_pictures(ids: list, folder: str) -> str:
    """Save pictures (by id) as PNG files in a folder, e.g. to look at them or hand them to 3D AI."""
    out = Path(folder).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for pic in ids:
        path = out / f"{pic}.png"
        path.write_bytes(api("image", "GET", f"api/pictures/{_q(pic)}"))
        saved.append(str(path))
    return "\n".join(saved)


def image_approve(ids: list, name: str) -> str:
    """Move chosen Staging pictures into the Library under a name (a character or an item)."""
    api("image", "POST", "api/staging/approve", {"ids": ids, "character": name})
    return f"Moved {len(ids)} picture(s) to the Library as '{name}'."


# ---------- 3D AI ----------

def mesh_make(picture: str, name: str, versions: int = 1) -> str:
    """Make 3D models (versions) from one picture file on this computer."""
    path = Path(picture).expanduser()
    if not path.is_file():
        raise ApiError(f"There's no file at {path}.")
    q = urllib.parse.urlencode({"name": name, "versions": versions, "filename": path.name})
    data = api("3d", "POST", f"api/make?{q}", raw=path.read_bytes())
    return f"Queued {len(data['jobs'])} version(s) of '{name}' (model {data['slug']})."


def mesh_bulk(folder: str, versions: int = 1, skip_existing: bool = True) -> str:
    """A model for every picture in a folder (named from the file names). The folder has to be inside one
    of 3D AI's allowed folders (its Bulk tab lists them)."""
    data = api("3d", "POST", "api/bulk", {"folder": str(Path(folder).expanduser()), "versions": versions,
                                          "skip_existing": skip_existing})
    return f"Bulk run {data['batch']}: {data['models']} models, {data['jobs']} jobs queued, {data['skipped']} skipped."


def mesh_status(wait_seconds: float = 0) -> str:
    deadline = time.time() + min(wait_seconds, MAX_WAIT)
    while True:
        s = api("3d", "GET", "api/status")
        if not (s.get("working") or s.get("waiting")) or time.time() >= deadline:
            break
        time.sleep(10)
    jobs = api("3d", "GET", "api/jobs")
    counts = {}
    for j in jobs:
        counts[j["status"]] = counts.get(j["status"], 0) + 1
    failed = [f"{j['name']}: {j.get('message', '')}" for j in jobs if j["status"] == "failed"][-10:]
    text = (f"TRELLIS problem: {s['problem']}\n" if s.get("problem") else "") + \
        f"Waiting {s.get('waiting', 0)}; working: {s.get('working') or 'nothing'}; all jobs: " + \
        ", ".join(f"{n} {st}" for st, n in sorted(counts.items()))
    return text + ("\nFailed:\n" + "\n".join(failed) if failed else "")


def mesh_models(search: str = "") -> str:
    models = [m for m in api("3d", "GET", "api/models") if search.lower() in m["name"].lower()]
    return "\n".join(f"{m['name']} ({m['slug']}): {sum(v['status'] == 'done' for v in m['versions'])} version(s) done"
                     for m in models) or "No models."


# ---------- what Claude sees ----------

S, N, B, A = {"type": "string"}, {"type": "number"}, {"type": "boolean"}, {"type": "array"}


def tool(name, function, description, properties=None, required=()):
    return {"name": name, "function": function, "description": description,
            "inputSchema": {"type": "object", "properties": properties or {}, "required": list(required)}}


TOOLS = [
    tool("aihub_status", status, "Which AI Hub tools are running and how much memory each uses."),
    tool("image_themes", image_themes, "Image AI's themes (id, name, what each is for)."),
    tool("image_make", image_make, "Make pictures with Image AI: a theme id and the prompt (just the subject; the "
         "theme adds its style). Queued; pass wait_seconds to wait for them.",
         {"theme": S, "prompt": S, "count": N, "wait_seconds": N}, ("theme", "prompt")),
    tool("image_job", image_job, "How a picture job is going (and its picture ids when done).",
         {"job": S, "wait_seconds": N}, ("job",)),
    tool("image_workflow_run", image_workflow_run, "Save a workflow (a list of items) and start it: each item is "
         "{theme, prompt, count, name}; its pictures go to Staging under its name. Re-using a name replaces "
         "that workflow. For bulk runs (dozens of characters or items).",
         {"name": S, "items": {"type": "array", "items": {"type": "object"}}, "start": B}, ("name", "items")),
    tool("image_workflow_status", image_workflow_status, "How a workflow run is going (by workflow id), with any "
         "problems. wait_seconds waits until it finishes (up to 10 minutes per call).",
         {"workflow": S, "wait_seconds": N}, ("workflow",)),
    tool("image_staging", image_staging, "Staging groups, or one group's picture ids (group = its folder name).",
         {"group": S}),
    tool("image_save_pictures", image_save_pictures, "Save pictures (by id) as PNG files in a folder on this "
         "computer, to look at them or to give them to 3D AI.", {"ids": A, "folder": S}, ("ids", "folder")),
    tool("image_approve", image_approve, "Move chosen Staging pictures (ids) to the Library under a name.",
         {"ids": A, "name": S}, ("ids", "name")),
    tool("mesh_make", mesh_make, "Make 3D models (GLB, TRELLIS.2) from one picture file. Several versions of the "
         "same name go into one model in the 3D Library. About 50 s each once TRELLIS is loaded.",
         {"picture": S, "name": S, "versions": N}, ("picture", "name")),
    tool("mesh_bulk", mesh_bulk, "A 3D model for every picture in a folder, named from the file names "
         "(skip_existing skips names already in the 3D Library).",
         {"folder": S, "versions": N, "skip_existing": B}, ("folder",)),
    tool("mesh_status", mesh_status, "3D AI's queue: what's waiting and working, totals, and recent failures. "
         "wait_seconds waits until the queue is empty (up to 10 minutes per call).", {"wait_seconds": N}),
    tool("mesh_models", mesh_models, "Models in the 3D Library (optionally only names containing a search word).",
         {"search": S}),
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
        return  # a notification: nothing to answer
    if method == "initialize":
        return reply(msg_id, {
            "protocolVersion": params.get("protocolVersion", PROTOCOL),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "aihub", "version": "1.0"},
            "instructions": "AI Hub runs the user's own AI tools on their Mac: Image AI (pictures from themes, "
                            "Staging, Library) and 3D AI (pictures into GLB models). Its queues are shared with the "
                            "pages the user watches. Check pictures before approving them.",
        })
    if method == "ping":
        return reply(msg_id, {})
    if method == "tools/list":
        return reply(msg_id, {"tools": [{k: v for k, v in t.items() if k != "function"} for t in TOOLS]})
    if method == "tools/call":
        found = BY_NAME.get(params.get("name"))
        if found is None:
            return reply(msg_id, error={"code": -32602, "message": f"No tool called {params.get('name')}."})
        try:
            text = found["function"](**(params.get("arguments") or {}))
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
