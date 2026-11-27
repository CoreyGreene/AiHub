"""What Talk can do when asked, through AiHub: say what's running, start or stop a tool, make a picture or a video,
and say how the queues are going. Each is a tool the model may call; the answer is a short line it can say."""

import json
import threading
import time

import httpx

from . import settings

NAMES = {"image": "Image AI", "3d": "3D AI", "code": "Code AI", "movie": "Movie AI", "talk": "Talk",
         "lights": "Lights AI"}


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


# ---------- notes: things said aloud, added to a file (playtest notes and the like) ----------

def _slug(name: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower().replace("notes", "").replace("file", "")).strip("-")


def _notes_file(name: str):
    """(name, path) of the notes called name. Names in settings' notes ({name: path}, e.g. game -> the game's
    docs/playtest-notes.md) go where they say; any other name is its own file in notes_folder (made when first
    used); no name is the general notes there (notes.md)."""
    from pathlib import Path

    files = {_slug(k): v for k, v in (settings.get().get("notes") or {}).items()}
    key = _slug(name)
    if key in files:
        return key, Path(files[key]).expanduser()
    folder = Path(settings.get()["notes_folder"]).expanduser()
    if not folder.is_absolute():
        folder = settings.ROOT / folder
    return (key or "general"), folder / f"{key or 'notes'}.md"


def list_notes() -> str:
    """Which notes there are, and how many lines each has."""
    from pathlib import Path

    found = {}
    for name, path in (settings.get().get("notes") or {}).items():
        found[_slug(name)] = Path(path).expanduser()
    folder = Path(settings.get()["notes_folder"]).expanduser()
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        found.setdefault("general" if path.stem == "notes" else path.stem, path)
    said = []
    for name, path in found.items():
        n = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("- ")) \
            if path.exists() else 0
        if n:
            said.append(f"{name} ({n})")
    return ("Notes: " + ", ".join(said)) if said else "There are no notes yet."


def add_note(note: str, file: str = "") -> str:
    """Add a note to the end of a notes file, under a heading for today, with the time."""
    note = " ".join((note or "").split()).strip()
    if not note:
        return "There was nothing to note."
    name, path = _notes_file(file)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else (
        f"# {name.replace('-', ' ').capitalize()} notes\n\nSaid aloud to Talk, newest at the bottom: one line each, "
        "the date above, the time before each.\n")
    day = time.strftime("%Y-%m-%d (%A)")
    if f"\n## {day}\n" not in text:
        text = text.rstrip("\n") + f"\n\n## {day}\n\n"
    text = text.rstrip("\n") + f"\n- {time.strftime('%H:%M')} {note}\n"
    path.write_text(text, encoding="utf-8")
    count = sum(1 for line in text.splitlines() if line.startswith("- "))
    return f"Added to the {name} notes ({count} so far): {note}"


def read_notes(file: str = "", how_many: int = 5) -> str:
    """The last few notes in a notes file, and how many there are."""
    name, path = _notes_file(file)
    if not path.exists():
        return f"The {name} notes are empty."
    notes = [line[2:] for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("- ")]
    last = notes[-max(1, min(int(how_many or 5), 20)):]
    return f"{len(notes)} {name} notes in all. The last {len(last)}: " + " | ".join(last)


def lights_status() -> str:
    """Which lights and groups there are, and how each light is, from Lights AI."""
    _running("lights", wait=30)
    data = _hub("GET", "/lights/api/lights")
    if not data.get("ready"):
        return "No lights are set up in Lights AI yet."
    out = []
    for home in data["homes"]:
        if not home["connected"]:
            out.append(f"Lights AI is still connecting to {home['name']}.")
        said = []
        for light in home["lights"]:
            if light["on"] is None:
                said.append(f"{light['name']}: no answer yet")
            elif not light["on"]:
                said.append(f"{light['name']}: off")
            else:
                warm = f", {light['kelvin']} kelvin" if light.get("has_temp") and light.get("kelvin") else ""
                said.append(f"{light['name']}: on at {light['brightness']} percent{warm}")
        out.append("; ".join(said) + ".")
        if home["groups"]:
            out.append("Groups: " + ", ".join(g["name"] for g in home["groups"]) + ".")
    return " ".join(out)


def set_lights(lights=None, on: bool | None = None, brightness: float | None = None,
               kelvin: int | None = None) -> str:
    """Turn lights on or off, dim them and/or change their colour temperature, through Lights AI."""
    _running("lights", wait=30)
    body = {"lights": lights or "all", "on": on, "brightness": brightness, "kelvin": kelvin}
    return _hub("POST", "/lights/api/set", {k: v for k, v in body.items() if v is not None}, timeout=60)["message"]


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
    _def("add_note", "Add a note to a notes file, for later. note: what the user said, in their words, tidied only a "
         "little. file: the name of the notes the user said (\"my game notes\" -> game, \"grocery list\" -> grocery, "
         "\"ideas\" -> ideas); each name is its own file, made when first used. Leave file empty when they named none.",
         {"note": {"type": "string"}, "file": {"type": "string"}}, ["note"]),
    _def("read_notes", "Read back the last few notes in one notes file (by its name, as for add_note), and how many.",
         {"file": {"type": "string"}, "how_many": {"type": "integer"}}),
    _def("list_notes", "Which notes files there are, and how many notes each has."),
    _def("lights_status", "The house lights (HALO Home): their names, the groups, and whether each light is on, how "
         "bright and how warm. Use it when asked about the lights, or to learn their names."),
    _def("set_lights", "Change the house lights. lights: which ones, as the user named them, a light or a group "
         "(e.g. [\"fireplace\", \"stair\"], [\"main 3\"]), or [\"all\"] for every light. Then only what the user asked "
         "to change: on (true or false), brightness (1 to 100 percent; \"dim it\" with no number: about 30), kelvin "
         "(colour temperature, 2700 = warm to 5000 = cool daylight; \"warmer\": 2700, \"cooler\": 4000 or more). "
         "Turning a light on with no brightness puts it back to how bright it was.",
         {"lights": {"type": "array", "items": {"type": "string"}},
          "on": {"type": "boolean"},
          "brightness": {"type": "number"},
          "kelvin": {"type": "integer"}}, ["lights"]),
]
_RUN = {"whats_running": whats_running, "start_tool": start_tool, "stop_tool": stop_tool,
        "make_picture": make_picture, "make_video": make_video, "how_are_jobs": how_are_jobs,
        "add_note": add_note, "read_notes": read_notes, "list_notes": list_notes,
        "lights_status": lights_status, "set_lights": set_lights}


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
