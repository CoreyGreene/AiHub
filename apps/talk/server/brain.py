"""One turn of a conversation: what was said in, the answer out, spoken a sentence at a time as it's written.

The thinking is Code AI's model (through AiHub: /code/api/chat, thinking off so it answers at once). When it asks for
one of the actions (actions.py), Talk does it and the model carries on. Each sentence is spoken (voice.py) as soon as
it's complete, so the first one plays while the rest is still being written.

turn() yields events, each a dict: {"say": sentence, "audio": base64 wav}, {"did": what an action did},
{"error": text}, and last {"done": True, "messages": the turn's messages to keep for the next turn}.
"""

import base64
import json
import re

import httpx

from . import actions, settings, voice

ROUNDS = 4  # model → actions → model ... at most this many times a turn
SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]?\s+|\n+")


def _speakable(text: str) -> str:
    """What reads well aloud: no markdown, code marks, links or emoji."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_#`>|~]+", "", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _say(text: str, voice_id: str) -> dict | None:
    clean = _speakable(text)
    if not re.search(r"\w", clean):
        return None
    return {"say": clean, "audio": base64.b64encode(voice.speak(clean, voice_id)).decode()}


def _ask(messages: list[dict], stop):
    """Stream the model's answer: yields ("answer", text), ("tool", call), ("error", text)."""
    actions._running("code")
    body = {"messages": messages, "model": settings.get()["think_model"], "thinking": "off",
            "tools": actions.DEFINITIONS}
    with httpx.stream("POST", settings.hub_url() + "/code/api/chat", json=body, timeout=httpx.Timeout(900)) as r:
        if r.status_code >= 400:
            yield "error", f"The model didn't answer ({r.status_code})."
            return
        for line in r.iter_lines():
            if stop():
                return
            if not line.strip():
                continue
            piece = json.loads(line)
            for kind in ("answer", "tool", "error"):
                if kind in piece:
                    yield kind, piece[kind]


def turn(history: list[dict], text: str, voice_id: str, stop=lambda: False):
    persona = settings.get()["persona"]
    messages = [{"role": "system", "content": persona}, *history, {"role": "user", "content": text}]
    kept = [{"role": "user", "content": text}]
    for _ in range(ROUNDS):
        said, held, calls = "", "", {}
        try:
            for kind, piece in _ask(messages, stop):
                if kind == "error":
                    yield {"error": piece}
                    break
                if kind == "tool":  # pieces of a call, put together by index
                    i = piece.get("index", len(calls))
                    c = calls.setdefault(i, {"id": piece.get("id") or f"call{i}", "name": "", "arguments": ""})
                    fn = piece.get("function") or {}
                    c["name"] += fn.get("name") or ""
                    args = fn.get("arguments")
                    c["arguments"] += args if isinstance(args, str) else json.dumps(args or {})
                    continue
                held += piece
                said += piece
                parts = SENTENCE_END.split(held)
                for sentence in parts[:-1]:  # every complete sentence: say it now
                    spoken = _say(sentence, voice_id)
                    if spoken:
                        yield spoken
                    if stop():
                        return
                held = parts[-1]
        except httpx.HTTPError as err:
            yield {"error": f"Couldn't reach the model ({type(err).__name__})."}
            return
        if held.strip() and not stop():
            spoken = _say(held, voice_id)
            if spoken:
                yield spoken
        if stop():
            return
        if not calls:
            kept.append({"role": "assistant", "content": said})
            break
        # do what it asked, tell it what happened, and let it carry on
        call_list = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                     for c in calls.values()]
        step = [{"role": "assistant", "content": said, "tool_calls": call_list}]
        for c in calls.values():
            result = actions.run(c["name"], c["arguments"])
            yield {"did": f"{c['name']}: {result}"}
            step.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": result})
        messages += step
        kept += step
    yield {"done": True, "messages": kept}
