"""Keeping Code AI's model (think_model, Gemma) loaded, so talking never waits for it to load.

When Talk starts, it starts Code AI and has it load the model, then asks Code AI every minute to keep holding it
(/code/api/model/warm). Anything else can still let it go when it needs the memory (another model, Code AI's
Settings, Stop): it isn't loaded again until you talk, or until Code AI is free after a "busy". If a bigger model
is in Code AI's memory or queue, it isn't replaced: the Talk page asks (state "bigger") and answer() takes the reply.

state: starting / loading / ready / none (let go; loads when you talk) / busy (loads when Code AI is free) /
bigger (asking) / kept (you kept the bigger one) / failed.
"""

import threading
import time

from . import actions, settings

RENEW = 60  # seconds between "keep holding it"
RETRY = 15  # seconds between tries while Code AI is busy

_status = {"state": "starting", "model": "", "bigger": "", "message": ""}
_want = {"load": True, "force": False}  # load it on the next try (and over a bigger model)
_wake = threading.Event()


def status() -> dict:
    return dict(_status)


def answer(load: bool) -> dict:
    """The reply to "a bigger model is loaded": load the talking model over it, or keep the bigger one."""
    if load:
        _want.update(load=True, force=True)
        _status.update(state="loading", message="")
        _wake.set()
    elif _status["state"] == "bigger":
        _status["state"] = "kept"
    return status()


def _try() -> float:
    """One try; how long until the next."""
    model = settings.get()["think_model"]
    load = _want["load"]
    if load:
        actions._running("code", wait=180)  # only when loading: a Code AI you stopped stays stopped
    data = actions._hub("POST", "/code/api/model/warm",
                        {"model": model, "load": load, "force": _want["force"]}, timeout=60)
    state = data["state"]
    _status.update(model=data.get("model", model), bigger=data.get("bigger", ""), message="")
    if state == "busy":
        _status["state"] = "busy"
        return RETRY
    _want.update(load=False, force=False)
    if not (state == "none" and _status["state"] in ("bigger", "kept")):  # still asking, or kept: say so
        _status["state"] = state
    return RETRY if state == "loading" else RENEW


def _keeper() -> None:
    time.sleep(2)  # let the hub see Talk running first
    while True:
        try:
            wait = _try()
        except Exception as err:  # Code AI stopped or not set up: say so, and only renew from now on
            if _want["load"]:
                _status.update(state="failed", message=str(err) or type(err).__name__)
            elif _status["state"] in ("ready", "loading"):
                _status["state"] = "none"
            _want.update(load=False, force=False)
            wait = RENEW
        _wake.wait(wait)
        _wake.clear()


def start() -> None:
    threading.Thread(target=_keeper, daemon=True).start()
