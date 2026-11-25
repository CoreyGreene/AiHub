"""Speech: a recording in, the words said in it out. Used by the hub's mic
buttons (AiHub sends /hub/api/listen here). Whisper through MLX, on a Mac.

    POST /api/transcribe   the recording is the body (webm, mp4, m4a, wav...)
                           -> {"text": "..."}
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parent.parent
_lock = threading.Lock()
_last_used = 0.0

SUFFIX = {"webm": ".webm", "mp4": ".mp4", "m4a": ".m4a", "mpeg": ".mp3", "ogg": ".ogg", "wav": ".wav", "x-wav": ".wav"}


def settings() -> dict:
    data = json.loads((ROOT / "server" / "settings.json").read_text())
    local = ROOT / "server" / "settings.local.json"
    if local.exists():
        data.update(json.loads(local.read_text()))
    if os.environ.get("AIHUB_MODELS_DIR"):
        data["models_dir"] = os.environ["AIHUB_MODELS_DIR"]
    return data


def model_folder() -> Path:
    s = settings()
    folder = Path(s["models_dir"]).expanduser()
    if not folder.is_absolute():
        folder = ROOT / folder
    return folder / s["model"]


def _unloader():
    """Let go of the model once nothing has been said for a while."""
    from mlx_whisper.transcribe import ModelHolder

    while True:
        time.sleep(30)
        idle = time.time() - _last_used
        with _lock:
            if ModelHolder.model is not None and idle > settings()["unload_after_minutes"] * 60:
                ModelHolder.model = ModelHolder.model_path = None
                import mlx.core as mx

                mx.clear_cache()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
threading.Thread(target=_unloader, daemon=True).start()


@app.get("/", response_class=HTMLResponse)
def page():
    return """<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Speech</title><body style="font:16px system-ui;background:#16161d;color:#ececf1;padding:16px">
<h1>Speech</h1><p>Turns what you say into text for the 🎤 buttons next to the prompt boxes.
It starts by itself when a mic is first tapped. There's nothing to do here.</p></body>"""


@app.post("/api/transcribe")
async def transcribe(request: Request) -> dict:
    global _last_used
    data = await request.body()
    if not data:
        raise HTTPException(400, "Nothing was recorded.")
    if len(data) > settings()["max_mb"] * 1024 * 1024:
        raise HTTPException(400, "That recording is too long.")
    folder = model_folder()
    if not (folder / "config.json").is_file():
        raise HTTPException(503, f"The Whisper model isn't here ({folder.name}). Put it in the SoundModels folder.")
    kind = request.headers.get("content-type", "").split(";")[0].split("/")[-1]
    with tempfile.NamedTemporaryFile(suffix=SUFFIX.get(kind, ".webm")) as f:
        f.write(data)
        f.flush()
        import mlx_whisper

        with _lock:
            _last_used = time.time()
            try:
                result = mlx_whisper.transcribe(
                    f.name, path_or_hf_repo=str(folder), language=settings()["language"] or None,
                    condition_on_previous_text=False,
                )
            except Exception as err:  # bad or empty audio: say so plainly
                raise HTTPException(400, f"Couldn't hear anything in that recording ({type(err).__name__}).")
            _last_used = time.time()
    return {"text": result["text"].strip()}
