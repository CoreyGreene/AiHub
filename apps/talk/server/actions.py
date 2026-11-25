"""What Talk can do when asked, through AiHub: say what's running, start or stop a tool, make a picture or a video,
and say how the queues are going. Each is a tool the model may call; the answer is a short line it can say."""

import json
import threading
import time

import httpx

from . import settings

NAMES = {"image": "Image AI", "3d": "3D AI", "code": "Code AI", "movie": "Movie AI", "talk": "Talk"}


def _hub(method: str, path: str, body: dict | None = None, timeout: float = 30) -> dict:
    r = httpx.request(method, settings.hub_url() + path, json=body, timeout=timeout)
    data = r.json() if r.content else {}
    if r.status_code >= 400:
        raise RuntimeError(data.get("detail") or f"{path} answered {r.status_code}")
    return data


def _gb(n: int) -> str:
    g = n / 2**30  # as Activity Monitor counts them: a 128 GB Mac is 128, not 137
    return f"{g:.0f} gigabytes" if g >= 10 else f"{g:.1f} gigabytes"


def _tool_id(name: str) -> str:
    n = (name or "").lower().replace(" ai", "").replace("-", "").strip()
    for tid, label in NAMES.items():
        if n in (tid, label.lower(), label.lower().replace(" ai", "")) or n.startswith(tid):
            return tid
    raise RuntimeError(f"There's no tool called {name}. The tools: Image AI, 3D AI, Code AI, Movie AI.")


def _running(tid: str, wait: float = 120) -> None:
    """Start a tool through the hub if it isn't running, and wait until it answers."""
    _hub("POST", f"/hub/api/apps/{tid}/start")
    end = time.time() + wait
    while time.time() < end:
        state = next(a["state"] for a in _hub("GET", "/hub/api/status")["apps"] if a["id"] == tid)
        if state == "running":
            return
        if state in ("failed", "not_set_up"):
            raise RuntimeError(f"{NAMES[tid]} didn't start.")
        time.sleep(1)
    raise RuntimeError(f"{NAMES[tid]} is taking too long to start.")


def whats_running() -> str:
    data = _hub("GET", "/hub/api/status")
    live = [f"{a['name']} ({_gb(a['memory'])})" for a in data["apps"]
            if a["state"] == "running" and a["memory"] >= 1e9 and a["id"] != "talk"]
    mac = data["mac"]
    return (("Running with a model loaded: " + ", ".join(live)) if live else "Nothing has a model loaded.") + \
        f" The Mac is using {_gb(mac['used'])} of {_gb(mac['total'])}."


def start_tool(name: str) -> str:
    tid = _tool_id(name)
    _running(tid)
    return f"{NAMES[tid]} is running."


def stop_tool(name: str) -> str:
    tid = _tool_id(name)
    if tid == "talk":
        return "Talk can't stop itself while you're talking to it."
    _hub("POST", f"/hub/api/apps/{tid}/stop")
    return f"{NAMES[tid]} is stopped."


def make_picture(prompt: str, theme: str = "") -> str:
    """In Image AI, with the theme asked for (or picture_theme), into Staging's Talk group, where it's kept and
    shown (Library → Staging), not New, which only the page that made a picture shows."""
    _running("image")
    themes = _hub("GET", "/image/api/themes")
    wanted = (theme or settings.get()["picture_theme"]).lower()
    pick = next((t for t in themes if wanted in (t["name"].lower(), t["id"])), None) \
        or next((t for t in themes if wanted and wanted in t["name"].lower()), None) or themes[0]
    group = settings.get()["picture_group"]
    _hub("POST", "/image/api/generate", {"theme": pick["id"], "prompt": prompt, "staging": group})
    return (f"Started a picture in Image AI with the {pick['name']} theme. When it's done it's in the Library, "
            f"under Staging, in {group}.")


def make_video(prompt: str) -> str:
    """In Movie AI; once it's made it's saved to the Talk character in its Library (else only the page that made a
    video shows it)."""
    _running("movie")
    themes = _hub("GET", "/movie/api/themes")
    if not themes:
        raise RuntimeError("Movie AI has no themes yet.")
    job = _hub("POST", "/movie/api/generate", {"theme": themes[0]["id"], "prompt": prompt})["job"]
    group = settings.get()["picture_group"]
    threading.Thread(target=_keep_videos, args=(job, group), daemon=True).start()
    return (f"Started a video in Movie AI with the {themes[0]['name']} theme. A clip takes a minute or two; it'll be "
            f"in Movie AI's Library under {group}.")


def _keep_videos(job: str, character: str) -> None:
    """When the video job is done, save its videos to a character, so they show in Movie AI's Library."""
    for _ in range(720):  # up to an hour
        time.sleep(5)
        try:
            status = _hub("GET", f"/movie/api/jobs/{job}")
        except Exception:
            return
        if status.get("status") not in ("waiting", "working"):
            for v in status.get("videos", []):
                try:
                    _hub("POST", f"/movie/api/videos/{v['video']}/save", {"character": character})
                except Exception:
                    pass
            return


def how_are_jobs() -> str:
    status = {a["id"]: a["state"] for a in _hub("GET", "/hub/api/status")["apps"]}
    said = []
    for tid, path in (("image", "/image/api/queue"), ("movie", "/movie/api/queue"), ("code", "/code/api/queue")):
        if status.get(tid) != "running":
            continue
        try:
            q = _hub("GET", path)
            n = len(q) if isinstance(q, list) else len(q.get("jobs", q.get("queue", [])) or [])
            said.append(f"{NAMES[tid]}: {n} waiting or being made" if n else f"{NAMES[tid]}: nothing in the queue")
        except Exception:
            continue
    return "; ".join(said) or "None of the tools with a queue is running."


def _def(name, about, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": about, "parameters": {
        "type": "object", "properties": props or {}, "required": required or []}}}


DEFINITIONS = [
    _def("whats_running", "Which AI tools are running with a model loaded, and how much of the Mac's memory is used."),
    _def("start_tool", "Start one of the tools: Image AI, 3D AI, Code AI or Movie AI.",
         {"name": {"type": "string"}}, ["name"]),
    _def("stop_tool", "Stop one of the tools (frees its memory): Image AI, 3D AI, Code AI or Movie AI.",
         {"name": {"type": "string"}}, ["name"]),
    _def("make_picture", "Make a picture in Image AI from a description. theme: optional, e.g. Becky Style.",
         {"prompt": {"type": "string"}, "theme": {"type": "string"}}, ["prompt"]),
    _def("make_video", "Make a short video with sound in Movie AI from a description of what happens.",
         {"prompt": {"type": "string"}}, ["prompt"]),
    _def("how_are_jobs", "How the queues are going: pictures, videos and Code AI questions waiting or being made."),
]
_RUN = {"whats_running": whats_running, "start_tool": start_tool, "stop_tool": stop_tool,
        "make_picture": make_picture, "make_video": make_video, "how_are_jobs": how_are_jobs}


def run(name: str, arguments) -> str:
    """Do what the model asked; a short line back (what happened, or what went wrong)."""
    try:
        args = json.loads(arguments or "{}") if isinstance(arguments, str) else dict(arguments or {})
        if name not in _RUN:
            return f"There's no tool called {name}."
        return _RUN[name](**args)
    except (TypeError, ValueError) as err:
        return f"Those arguments don't fit {name} ({err})."
    except Exception as err:  # a tool that failed: told to the model, which says so
        return f"That didn't work: {err}"
