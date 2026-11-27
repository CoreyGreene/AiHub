"""The models, each in its own program (mlx_lm's server, see model_server.py), on its own port.

One model works on the queue's questions at a time. Talk's model (held with keep()) may stay loaded beside it, but
only while both fit with headroom_gb of the Mac's memory still free: otherwise it's let go to make room.

ensure() loads the model a question asks for (letting go of others as above), stream() asks it and yields the
answer as it comes, unload() lets go, let_go() frees memory for another tool (the hub's make-room).
"""

import atexit
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import settings

GB = 1024**3
_lock = threading.Lock()
_load_lock = threading.Lock()  # one load at a time (the queue's worker, Talk's chat, Talk's warm-up)
_servers: dict[str, dict] = {}  # model id -> {proc, port, state (loading / ready), used (time), busy (streams)}
_keep = {"id": None, "until": 0.0}  # a model held in memory for Talk while it renews the hold (keep())
_sizes: dict[str, int] = {}


class ModelError(Exception):
    pass


def _url(path: str, model_id: str) -> str:
    return f"http://127.0.0.1:{_servers[model_id]['port']}{path}"


def _alive(model_id: str) -> bool:
    server = _servers.get(model_id)
    return server is not None and server["proc"].poll() is None


def loaded_ids() -> list[str]:
    """The models in memory (or loading), the one used last first."""
    with _lock:
        return sorted((i for i in _servers if _alive(i)), key=lambda i: -_servers[i]["used"])


def is_ready(model_id: str) -> bool:
    with _lock:
        return _alive(model_id) and _servers[model_id]["state"] == "ready"


def pids() -> list[int]:
    with _lock:
        return [s["proc"].pid for i, s in _servers.items() if _alive(i)]


def loaded() -> dict:
    """The model in memory used last (or loading), for the top of the page; "also": the other one, by name."""
    ids = loaded_ids()
    if not ids:
        return {"id": None, "name": None, "state": "none", "pid": None, "also": []}
    with _lock:
        server = _servers.get(ids[0])
        if server is None:
            return {"id": None, "name": None, "state": "none", "pid": None, "also": []}
        m = settings.model(ids[0]) or {}
        return {"id": ids[0], "name": m.get("name", ids[0]), "state": server["state"], "pid": server["proc"].pid,
                "also": [(settings.model(i) or {}).get("name", i) for i in ids[1:]]}


def _stop(model_id: str) -> None:
    with _lock:
        server = _servers.pop(model_id, None)
    if server is not None and server["proc"].poll() is None:
        server["proc"].terminate()
        try:
            server["proc"].wait(timeout=20)
        except subprocess.TimeoutExpired:
            server["proc"].kill()
            server["proc"].wait()


def unload(but: str | None = None) -> None:
    """Let go of every model (but this one)."""
    for model_id in list(_servers):
        if model_id != but:
            _stop(model_id)


def keep(model_id: str | None, minutes: float = 5) -> None:
    """Hold this model in memory: it isn't let go when the queue is idle, until the hold runs out (Talk renews it
    every minute while it runs). It's still let go when another model needs its room, or by Settings or Stop.
    None: no hold."""
    _keep.update(id=model_id, until=time.time() + minutes * 60 if model_id else 0.0)


def kept() -> str | None:
    return _keep["id"] if time.time() < _keep["until"] else None


def size(model_id: str) -> int:
    """The model's files, in bytes: how big it is in memory, near enough."""
    m = settings.model(model_id or "")
    if m is None:
        return 0
    if m["path"] not in _sizes:
        _sizes[m["path"]] = sum(f.stat().st_size for f in Path(m["path"]).rglob("*") if f.is_file())
    return _sizes[m["path"]]


def free_bytes() -> int:
    """The Mac's memory not in use (as Activity Monitor counts used: apps + wired + compressed)."""
    total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
    vm = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
    page = int(re.search(r"page size of (\d+)", vm).group(1))
    pages = {k.strip(): int(v.strip().rstrip(".")) for k, v in
             (line.split(":") for line in vm.splitlines()[1:] if ":" in line)}
    used = (pages.get("Anonymous pages", 0) - pages.get("Pages purgeable", 0) + pages.get("Pages wired down", 0)
            + pages.get("Pages occupied by compressor", 0)) * page
    return total - used


def fits(model_id: str) -> bool:
    """Would this model load with headroom_gb of memory still free (beside what's loaded now)?"""
    return free_bytes() - size(model_id) >= settings.get()["headroom_gb"] * GB


def let_go(need: int, in_use: set[str]) -> list[str]:
    """Free about `need` bytes for another tool: models no question is using, the queue's first, Talk's last.
    The names of those let go."""
    held = kept()
    order = sorted((i for i in loaded_ids() if i not in in_use), key=lambda i: i == held)
    freed, names = 0, []
    for model_id in order:
        if freed >= need:
            break
        with _lock:
            busy = model_id in _servers and _servers[model_id]["busy"]
        if busy:
            continue
        freed += size(model_id)
        names.append((settings.model(model_id) or {}).get("name", model_id))
        _stop(model_id)
    return names


# when CodeAi stops (Ctrl+C), the models' programs stop with it
atexit.register(unload)


def ensure(model_id: str, on_stage=lambda stage: None) -> None:
    """Have this model loaded and answering. Waits while it loads (up to 15 minutes)."""
    with _load_lock:
        _ensure(model_id, on_stage)


def _ensure(model_id: str, on_stage) -> None:
    m = settings.model(model_id)
    if m is None:
        raise ModelError(f"There's no model '{model_id}' on this computer.")
    if is_ready(model_id):
        with _lock:
            _servers[model_id]["used"] = time.time()
        return
    _stop(model_id)  # one that stopped, or never finished loading
    held = kept()
    for other in loaded_ids():
        # one model works on the queue at a time; Talk's model or the working one stays beside it only if it fits
        if other != held and model_id != held:
            _stop(other)
    for other in loaded_ids():
        if not fits(model_id):
            _stop(other)
    on_stage("loading")
    s = settings.get()
    log = open(settings.folder("logs_dir") / "model.log", "a")
    log.write(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} loading {m['name']} ({m['path']})\n")
    log.flush()
    env = {**os.environ, "CODEAI_CACHE_GB": str(s["cache_gb"])}
    with _lock:
        taken = {srv["port"] for srv in _servers.values()}
    port = next(p for p in (s["model_port"], s["model_port"] + 1) if p not in taken)
    proc = subprocess.Popen(
        [sys.executable, "-m", "server.model_server", "--model", m["path"], "--host", "127.0.0.1",
         "--port", str(port), "--prompt-cache-size", str(s["prompt_cache_size"]), *m.get("server_args", [])],
        cwd=settings.ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    with _lock:
        _servers[model_id] = {"proc": proc, "port": port, "state": "loading", "used": time.time(), "busy": 0}
    for _ in range(900):
        if proc.poll() is not None:
            _stop(model_id)
            raise ModelError(f"{m['name']} stopped while loading (see logs/model.log).")
        try:
            urllib.request.urlopen(_url("/v1/models", model_id), timeout=2)
            with _lock:
                _servers[model_id]["state"] = "ready"
            return
        except (urllib.error.URLError, OSError, KeyError):
            time.sleep(1)
    _stop(model_id)
    raise ModelError(f"{m['name']} didn't finish loading in 15 minutes.")


def stream(model_id: str, messages: list[dict], template: dict, stop: threading.Event, tools: list | None = None,
           cut=lambda: False):
    """Ask that model (loaded with ensure()), marked busy meanwhile so let_go() leaves it. Yields ("thinking", text), ("answer", text) and ("tool", call) pieces as they come,
    then ("finish", reason). template: settings for the model's chat template (its thinking level). Stops early
    when `stop` is set (finish "stopped"), or when cut() says so (finish "budget": its thinking budget is used up)."""
    body = {
        "messages": messages,
        "max_tokens": settings.get()["max_tokens"],
        "stream": True,
        "chat_template_kwargs": template,
    }
    if tools:
        body["tools"] = tools
    with _lock:
        if model_id not in _servers:
            raise ModelError("The model was let go before it could answer. Ask again.")
        _servers[model_id]["busy"] += 1
        _servers[model_id]["used"] = time.time()
        url = _url("/v1/chat/completions", model_id)
    try:
        yield from _stream(url, body, stop, cut)
    finally:
        with _lock:
            if model_id in _servers:
                _servers[model_id]["busy"] -= 1


def _stream(url: str, body: dict, stop: threading.Event, cut):
    request = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    split = _ThinkSplitter()
    finish = None
    try:
        response = urllib.request.urlopen(request, timeout=3600)
    except urllib.error.HTTPError as err:
        raise ModelError(f"The model refused the question: {err.read().decode(errors='replace')[:300]}")
    with response:
        for raw in response:
            if stop.is_set():
                finish = "stopped"
                break
            if cut():
                finish = "budget"
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            choice = (json.loads(data).get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            reasoning = delta.get("reasoning") or delta.get("reasoning_content")
            if reasoning:
                yield "thinking", reasoning
            if delta.get("content"):
                yield from split.feed(delta["content"])
            for call in delta.get("tool_calls") or []:
                yield "tool", call
            finish = choice.get("finish_reason") or finish
    yield "finish", finish or "stop"


class _ThinkSplitter:
    """Some models write their thinking into the answer between <think> and </think>: move it to the thinking."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self.inside = False
        self.held = ""

    def feed(self, text: str):
        text = self.held + text
        self.held = ""
        while text:
            tag = self.CLOSE if self.inside else self.OPEN
            at = text.find(tag)
            if at < 0:
                # keep back a piece that might be the start of a tag
                keep = next((n for n in range(len(tag) - 1, 0, -1) if text.endswith(tag[:n])), 0)
                out, self.held = (text[:-keep], text[-keep:]) if keep else (text, "")
                if out:
                    yield ("thinking" if self.inside else "answer"), out
                return
            if at:
                yield ("thinking" if self.inside else "answer"), text[:at]
            self.inside = not self.inside
            text = text[at + len(tag):]
