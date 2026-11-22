"""The model: one at a time, in its own program (mlx_lm's server, see model_server.py).

ensure() loads the model a question asks for (stopping another first), stream() asks it and yields the answer as it
comes, unload() lets it go. Only the queue's one worker calls ensure/stream, so there's never more than one model.
"""

import atexit
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from . import settings

_lock = threading.Lock()
_current = {"id": None, "proc": None, "state": "none"}  # state: none / loading / ready


class ModelError(Exception):
    pass


def _url(path: str) -> str:
    return f"http://127.0.0.1:{settings.get()['model_port']}{path}"


def loaded() -> dict:
    """Which model is in memory (or loading), for the top of the page."""
    with _lock:
        proc = _current["proc"]
        if proc is None or proc.poll() is not None:
            return {"id": None, "name": None, "state": "none", "pid": None}
        m = settings.model(_current["id"]) or {}
        return {"id": _current["id"], "name": m.get("name", _current["id"]), "state": _current["state"], "pid": proc.pid}


def unload() -> None:
    with _lock:
        proc = _current["proc"]
        _current.update(id=None, proc=None, state="none")
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


# when CodeAi stops (Ctrl+C), the model's program stops with it
atexit.register(unload)


def ensure(model_id: str, on_stage=lambda stage: None) -> None:
    """Have this model loaded and answering. Waits while it loads (up to 15 minutes)."""
    m = settings.model(model_id)
    if m is None:
        raise ModelError(f"There's no model '{model_id}' on this computer.")
    with _lock:
        proc = _current["proc"]
        if _current["id"] == model_id and proc is not None and proc.poll() is None and _current["state"] == "ready":
            return
    unload()
    on_stage("loading")
    s = settings.get()
    log = open(settings.folder("logs_dir") / "model.log", "a")
    log.write(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} loading {m['name']} ({m['path']})\n")
    log.flush()
    env = {**os.environ, "CODEAI_CACHE_GB": str(s["cache_gb"])}
    proc = subprocess.Popen(
        [sys.executable, "-m", "server.model_server", "--model", m["path"], "--host", "127.0.0.1",
         "--port", str(s["model_port"]), "--prompt-cache-size", str(s["prompt_cache_size"]), *m.get("server_args", [])],
        cwd=settings.ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    with _lock:
        _current.update(id=model_id, proc=proc, state="loading")
    for _ in range(900):
        if proc.poll() is not None:
            unload()
            raise ModelError(f"{m['name']} stopped while loading (see logs/model.log).")
        try:
            urllib.request.urlopen(_url("/v1/models"), timeout=2)
            with _lock:
                _current["state"] = "ready"
            return
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    unload()
    raise ModelError(f"{m['name']} didn't finish loading in 15 minutes.")


def stream(messages: list[dict], template: dict, stop: threading.Event, tools: list | None = None):
    """Ask the loaded model. Yields ("thinking", text), ("answer", text) and ("tool", call) pieces as they come,
    then ("finish", reason). template: settings for the model's chat template (its thinking level). Stops early
    when `stop` is set."""
    body = {
        "messages": messages,
        "max_tokens": settings.get()["max_tokens"],
        "stream": True,
        "chat_template_kwargs": template,
    }
    if tools:
        body["tools"] = tools
    request = urllib.request.Request(_url("/v1/chat/completions"), json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
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
