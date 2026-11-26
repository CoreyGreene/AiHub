"""Sound AI's web page, generation job, and local WAV library."""

import json
import logging
import re
import shutil
import tempfile
import time
from pathlib import Path
from random import randrange
from threading import Lock, Thread
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import generation

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
jobs_lock = Lock()
library_lock = Lock()
job: dict | None = None
log = logging.getLogger("uvicorn.error")


class SoundRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1500)
    seconds: float = Field(default=3, ge=1, le=30)
    model: str = generation.MODEL


class SaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def read_clip(folder: Path) -> dict | None:
    try:
        if (folder / "sound.wav").is_file():
            return json.loads((folder / "clip.json").read_text())
    except (FileNotFoundError, ValueError):
        pass
    return None


def clip_folder(clip_id: UUID) -> Path:
    return OUTPUTS / clip_id.hex


def get_clip(clip_id: UUID) -> tuple[Path, dict]:
    folder = clip_folder(clip_id)
    clip = read_clip(folder)
    if clip is None:
        raise HTTPException(404, "That sound is no longer here.")
    return folder, clip


def write_clip(folder: Path, clip: dict) -> None:
    temporary = folder / "clip.json.tmp"
    temporary.write_text(json.dumps(clip, ensure_ascii=False) + "\n")
    temporary.replace(folder / "clip.json")


def run_sound(clip: dict) -> None:
    def progress(stage: str, step: int) -> None:
        with jobs_lock:
            job.update(stage=stage, step=step)

    try:
        OUTPUTS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=OUTPUTS, prefix=".working-") as working:
            folder = Path(working)
            generation.make(clip["prompt"], clip["seconds"], clip["seed"], folder / "sound.wav", progress)
            write_clip(folder, clip)
            with library_lock:
                folder.replace(OUTPUTS / clip["id"])
    except Exception:
        log.exception("Sound AI could not generate a sound")
        with jobs_lock:
            job.update(state="error", stage="Couldn't generate this sound. Check the Sound AI log for details.")
    else:
        with jobs_lock:
            job.update(state="done", stage="Sound ready")


@app.get("/api/status")
def status() -> dict:
    with jobs_lock:
        current = dict(job) if job is not None else None
    return {"model": {"id": generation.MODEL, "name": generation.MODEL_NAME},
            "model_ready": generation.model_ready(), "job": current}


@app.post("/api/generate", status_code=202)
def generate(request: SoundRequest) -> dict:
    global job
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(422, "Describe the sound you want to make.")
    if request.model != generation.MODEL:
        raise HTTPException(422, "That sound model isn't available.")
    if not generation.model_ready():
        raise HTTPException(503, "Stable Audio 3 Small SFX is missing files in SoundModels.")
    with jobs_lock:
        if job and job["state"] == "working":
            raise HTTPException(409, "Sound AI is already making a sound.")
        clip = {"id": uuid4().hex, "prompt": prompt, "seconds": request.seconds, "model": request.model,
                "seed": randrange(2**31), "created": time.time(), "name": "", "saved": False}
        job = {"id": clip["id"], "state": "working", "stage": "Loading model",
               "step": 0, "steps": generation.STEPS}
        Thread(target=run_sound, args=(clip,), daemon=True).start()
        return dict(job)


@app.get("/api/sounds")
def sounds() -> list[dict]:
    with library_lock:
        clips = [clip for folder in OUTPUTS.glob("[0-9a-f]*") if (clip := read_clip(folder))]
    return sorted(clips, key=lambda clip: clip["created"], reverse=True)


@app.delete("/api/recent")
def delete_recent() -> dict:
    removed = []
    with library_lock:
        for folder in OUTPUTS.glob("[0-9a-f]*"):
            clip = read_clip(folder)
            if clip and clip.get("saved") is False:
                shutil.rmtree(folder)
                removed.append(clip["id"])
    return {"removed": removed}


@app.put("/api/sounds/{clip_id}")
def save(clip_id: UUID, request: SaveRequest) -> dict:
    name = request.name.strip()
    if not name:
        raise HTTPException(422, "Give the sound a name.")
    with library_lock:
        folder, clip = get_clip(clip_id)
        clip.update(name=name, saved=True)
        write_clip(folder, clip)
    return clip


@app.api_route("/api/sounds/{clip_id}/audio", methods=["GET", "HEAD"])
def audio(clip_id: UUID, download: bool = False) -> FileResponse:
    folder, clip = get_clip(clip_id)
    name = clip["name"] or f"sound-{clip_id.hex[:8]}"
    filename = re.sub(r'[\\/\x00-\x1f]', "-", name) + ".wav" if download else None
    return FileResponse(folder / "sound.wav", media_type="audio/wav", filename=filename)


@app.delete("/api/sounds/{clip_id}", status_code=204)
def delete(clip_id: UUID) -> None:
    with library_lock:
        folder, _ = get_clip(clip_id)
        shutil.rmtree(folder)


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
