"""Conversations, one JSON file each in history/ (History tab).

A conversation: id, title (its first question), model, created, updated, and messages. A message: role ("user" or
"assistant"), content, from ("you" or "claude", who asked), and for answers: thinking, model, seconds, tokens,
per_second, and status ("done", "stopped" or "failed").
"""

import json
import re
import threading
import time
import uuid

from . import settings

_lock = threading.Lock()


def _path(conv_id: str):
    if not re.fullmatch(r"[0-9a-f]{32}", conv_id or ""):
        raise KeyError(conv_id)
    return settings.folder("history_dir") / f"{conv_id}.json"


def _save(conv: dict) -> None:
    path = _path(conv["id"])
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(conv, indent=1, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def get(conv_id: str) -> dict | None:
    try:
        path = _path(conv_id)
    except KeyError:
        return None
    with _lock:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def create(first_question: str, model_id: str) -> dict:
    title = " ".join(first_question.split())
    conv = {
        "id": uuid.uuid4().hex,
        "title": title if len(title) <= 80 else title[:77] + "…",
        "model": model_id,
        "created": time.time(),
        "updated": time.time(),
        "messages": [],
    }
    with _lock:
        _save(conv)
    return conv


def add(conv_id: str, message: dict) -> None:
    with _lock:
        path = _path(conv_id)
        conv = json.loads(path.read_text(encoding="utf-8"))
        conv["messages"].append(message)
        conv["updated"] = time.time()
        if message["role"] == "assistant" and message.get("model"):
            conv["model"] = message["model"]
        _save(conv)


def update_message(conv_id: str, index: int, **changes) -> dict:
    """Change one saved message (e.g. mark an answer's file changes undone); returns it."""
    with _lock:
        path = _path(conv_id)
        conv = json.loads(path.read_text(encoding="utf-8"))
        conv["messages"][index].update(changes)
        _save(conv)
        return conv["messages"][index]


def listing() -> list[dict]:
    """Every conversation, newest first, without the messages."""
    out = []
    with _lock:
        for path in settings.folder("history_dir").glob("*.json"):
            try:
                conv = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            out.append({
                "id": conv["id"], "title": conv["title"], "model": conv["model"],
                "created": conv["created"], "updated": conv["updated"],
                "questions": sum(1 for m in conv["messages"] if m["role"] == "user"),
            })
    return sorted(out, key=lambda c: c["updated"], reverse=True)


def delete(conv_id: str) -> bool:
    with _lock:
        try:
            path = _path(conv_id)
        except KeyError:
            return False
        if not path.exists():
            return False
        path.unlink()
        return True
