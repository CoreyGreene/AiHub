"""The web server: serves the page in web/ and a small JSON API under /api."""

import asyncio
import io
import time
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import generation, gpu, jobs, lock, settings, themes, uploads, videos

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
# Changes on every server start. The page asks for app.css and app.js with
# it attached, so a restart always gets fresh files, never old cached ones.
STARTED = str(int(time.time()))

app = FastAPI(title="MovieAi")


@app.middleware("http")
async def code_lock(request, call_next):
    # With the lock on, a browser without the code's cookie sees only the
    # lock page; everything else (videos too) is turned away.
    path = request.url.path
    if lock.is_open(request.cookies.get(lock.COOKIE)) or path == "/api/unlock":
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "locked"}, status_code=401)
    if path in ("/", "/index.html"):
        return FileResponse(WEB_DIR / "lock.html")
    return Response("Locked", status_code=401)


class UnlockRequest(BaseModel):
    code: str


@app.post("/api/unlock")
async def unlock(req: UnlockRequest, response: Response) -> dict:
    """The lock page sends the code here. A wrong code is an everyday
    answer ("open": false), not an error."""
    if not lock.is_on():
        return {"open": True}
    try:
        right = lock.check(req.code.strip())
    except lock.Wait:
        return {"open": False, "message": "Too many wrong codes. Wait a minute, then try again."}
    if not right:
        await asyncio.sleep(1)  # slows down guessing
        return {"open": False, "message": "That's not the code. Try again."}
    response.set_cookie(lock.COOKIE, lock.token(), max_age=lock.LOCK_DAYS * 86400, httponly=True, samesite="lax")
    return {"open": True}


@app.middleware("http")
async def no_stale_page(request, call_next):
    # Make browsers (phones especially) check for a newer page every time,
    # so a reload always shows the latest change.
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/custom")
def custom_start() -> dict:
    """Where the Custom tab starts: model, words and video settings."""
    start = dict(settings.get()["custom"])
    models = generation.choices()["models"]
    if start["model"] not in models:
        start["model"] = models[0] if models else ""
    return {k: v for k, v in start.items() if k not in ("backend", "model_config")}


class LoraChoice(BaseModel):
    file: str
    weight: float


class CustomChoice(BaseModel):
    """The Custom tab: your own theme for these videos (no theme file)."""
    model: str
    loras: list[LoraChoice] = []
    prompt_before: str = ""
    prompt_after: str = ""
    negative: str = ""
    width: int
    height: int
    frames: int
    fps: int
    steps: int
    guidance: float
    scheduler: str


class ThemeWords(BaseModel):
    """The Advanced tab: the theme's words, changed for these videos only."""
    prompt_before: str = ""
    prompt_after: str = ""
    negative: str = ""


class GenerateRequest(BaseModel):
    theme: str = ""  # not used when custom is given
    prompt: str
    count: int = 1
    words: ThemeWords | None = None  # Advanced: in place of the theme's own
    custom: CustomChoice | None = None


@app.get("/api/themes")
def list_themes() -> list[dict]:
    return themes.public_list()


@app.get("/api/themes/details")
def theme_details() -> list[dict]:
    """Every theme in full: what it adds to the prompt, model, LoRAs, settings."""
    return [{"id": tid, **generation.describe(t)} for tid, t in themes.load().items()]


@app.get("/api/themes/choices")
def theme_choices() -> dict:
    """The model and LoRA files here, and the samplers, for changing a theme."""
    return generation.choices()


def _check_model_and_loras(model: str, loras: list[LoraChoice]) -> dict:
    """The model and LoRAs must be files that are here, each LoRA once."""
    found = generation.choices()
    if model not in found["models"]:
        raise HTTPException(400, "Pick a model that's in the models folder.")
    if len({lora.file for lora in loras}) < len(loras):
        raise HTTPException(400, "The same LoRA is in the list twice. Remove one.")
    for lora in loras:
        if lora.file not in found["loras"]:
            raise HTTPException(400, f"The LoRA {lora.file} isn't in the LoRA folder.")
        if not -2 <= lora.weight <= 2:
            raise HTTPException(400, "LoRA strength must be between -2 and 2.")
    return found


def _check_video_settings(req, found: dict) -> None:
    """Size, length, steps, guidance and sampler (a theme change or a custom video)."""
    for label, value in (("Width", req.width), ("Height", req.height)):
        if not 256 <= value <= 1920 or value % 16:
            raise HTTPException(400, f"{label} must be 256 to 1920, and divide by 16.")
    if not 1 <= req.frames <= 241:
        raise HTTPException(400, "Frames must be 1 to 241.")
    if not 4 <= req.fps <= 60:
        raise HTTPException(400, "Frames a second must be 4 to 60.")
    if not 1 <= req.steps <= 100:
        raise HTTPException(400, "Steps must be 1 to 100.")
    if not 0 <= req.guidance <= 30:
        raise HTTPException(400, "Guidance must be 0 to 30.")
    if req.scheduler not in found["schedulers"]:
        raise HTTPException(400, "Pick one of the samplers in the list.")


def _tidy(words: str) -> str:
    return " ".join(words.split()).strip(" ,")


def _prompt_template(before: str, after: str) -> str:
    """Your prompt goes between the words before and after it."""
    return ", ".join(w for w in (_tidy(before), "{prompt}", _tidy(after)) if w)


class ThemeChange(BaseModel):
    name: str
    hint: str = ""
    prompt_before: str = ""
    prompt_after: str = ""
    negative: str = ""
    model: str
    loras: list[LoraChoice] = []
    width: int
    height: int
    frames: int
    fps: int
    steps: int
    guidance: float
    scheduler: str


def _theme_keys(req: ThemeChange) -> dict:
    """The theme file's keys from the Theme tab's form, once checked."""
    name = " ".join(req.name.split())
    if not name:
        raise HTTPException(400, "Give the theme a name.")
    found = _check_model_and_loras(req.model, req.loras)
    _check_video_settings(req, found)
    return {
        "name": name,
        "hint": " ".join(req.hint.split()),
        "prompt": _prompt_template(req.prompt_before, req.prompt_after),
        "negative": _tidy(req.negative),
        "model": req.model,
        "loras": [{"file": l.file, "weight": l.weight} for l in req.loras],
        "width": req.width,
        "height": req.height,
        "frames": req.frames,
        "fps": req.fps,
        "steps": req.steps,
        "guidance": req.guidance,
        "scheduler": req.scheduler,
    }


@app.put("/api/themes/{theme_id}")
def change_theme(theme_id: str, req: ThemeChange) -> dict:
    """Save changes to a theme file. The next video uses them."""
    if themes.get(theme_id) is None:
        raise HTTPException(404, "That theme isn't there any more. Reload the page.")
    themes.save(theme_id, _theme_keys(req))
    return {"id": theme_id, **generation.describe(themes.get(theme_id))}


@app.post("/api/themes")
def new_theme(req: ThemeChange) -> dict:
    """Make a new theme file from the Theme tab's New form."""
    keys = _theme_keys(req)
    if keys["name"].lower() in {t["name"].lower() for t in themes.public_list()}:
        raise HTTPException(400, "There's already a theme with that name. Pick another.")
    start = settings.get()["custom"]
    theme_id = themes.create({
        "name": keys.pop("name"),
        "hint": keys.pop("hint"),
        "backend": start["backend"],
        "model_config": start["model_config"],
        **keys,
    })
    return {"id": theme_id, **generation.describe(themes.get(theme_id))}


@app.get("/api/files/{kind}/{name}/check")
def check_upload(kind: str, name: str, size: int) -> dict:
    """Asked before an upload starts, so a file that would be refused
    (bad name, already there, no room) is told at once, not after 30 GB."""
    try:
        uploads.target(kind, name, size)
    except uploads.Refused as err:
        raise HTTPException(400, str(err))
    return {"ok": True}


@app.put("/api/files/{kind}/{name}")
async def upload_file(kind: str, name: str, request: Request) -> dict:
    """Add a model or LoRA from the page: the file is the request body.
    kind is "model" or "lora"; it goes in that folder."""
    size = request.headers.get("content-length")
    try:
        path = await uploads.receive(kind, name, int(size) if size else None, request.stream())
    except uploads.Refused as err:
        raise HTTPException(400, str(err))
    return {"file": path.name, **generation.choices()}


@app.post("/api/generate")
def generate(req: GenerateRequest) -> dict:
    """Adds a video to the queue; the page then asks /api/jobs/{job} for progress."""
    theme_id = "custom" if req.custom else req.theme
    theme = None if req.custom else themes.get(req.theme)
    if theme is None and not req.custom:
        raise HTTPException(400, "That theme isn't there any more. Reload the page.")
    prompt = " ".join(req.prompt.split())
    if not prompt:
        raise HTTPException(400, "Type a prompt first.")
    most = settings.get()["max_videos"]
    if not 1 <= req.count <= most:
        raise HTTPException(400, f"Pick between 1 and {most} videos.")
    if req.custom:
        # Your own theme, made from the Custom tab (nothing is saved to a file).
        c = req.custom
        _check_video_settings(c, _check_model_and_loras(c.model, c.loras))
        start = settings.get()["custom"]
        theme = {
            "name": "Custom",
            "backend": start["backend"],
            "model_config": start["model_config"],
            "model": c.model,
            "loras": [{"file": l.file, "weight": l.weight} for l in c.loras],
            "prompt": _prompt_template(c.prompt_before, c.prompt_after),
            "negative": _tidy(c.negative),
            **{key: getattr(c, key) for key in ("width", "height", "frames", "fps", "steps", "guidance", "scheduler")},
        }
    elif req.words:
        # The theme's words as changed on the Advanced tab (the file stays as it is).
        w = req.words
        theme = {**theme, "prompt": _prompt_template(w.prompt_before, w.prompt_after), "negative": _tidy(w.negative)}
    try:
        return {"job": jobs.submit(theme_id, theme, prompt, req.count)}
    except jobs.QueueFull as err:
        raise HTTPException(429, str(err))


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    found = jobs.status(job_id)
    if found is None:
        raise HTTPException(404, "That video job isn't known (the server may have restarted).")
    return found


@app.get("/api/queue")
def queue_list() -> list[dict]:
    """Every video job being made or waiting, in order."""
    return jobs.listing()


@app.delete("/api/queue/{job_id}")
def queue_remove(job_id: str) -> dict:
    if not jobs.remove(job_id):
        raise HTTPException(404, "That job isn't in the queue any more.")
    return {"status": "removed"}


@app.get("/api/characters")
def characters() -> list[dict]:
    return videos.list_characters()


@app.get("/api/characters/{folder}")
def character(folder: str) -> dict:
    found = videos.character(folder)
    if found is None:
        raise HTTPException(404, "That character isn't in the library.")
    # Show the theme's name where it still exists, else its id.
    names = {t["id"]: t["name"] for t in themes.public_list()} | {"custom": "Custom"}
    for vid in found["videos"]:
        vid["theme"] = names.get(vid["theme"], vid["theme"])
    return found


@app.get("/api/videos/{vid_id}")
def video(vid_id: str, download: bool = False) -> FileResponse:
    path = videos.find(vid_id)
    if path is None:
        raise HTTPException(404, "That video isn't here any more.")
    # download=1 makes the browser save the file instead of playing it.
    return FileResponse(path, media_type="video/mp4", filename=_file_name(path) if download else None)


@app.get("/api/videos/{vid_id}/poster")
def poster(vid_id: str) -> FileResponse:
    """The video's first frame, shown before it plays and in the Library."""
    path = videos.find(vid_id, ".jpg")
    if path is None:
        raise HTTPException(404, "That video isn't here any more.")
    return FileResponse(path, media_type="image/jpeg")


def _file_name(path: Path) -> str:
    who = path.parent.name if videos.is_saved(path) else "movieai"
    return f"{who}-{path.stem[:8]}.mp4"


@app.get("/api/videos-zip")
def videos_zip(ids: str, name: str = "") -> Response:
    """Several videos in one zip file, named after the character if one
    was typed (e.g. grim-the-goblin.zip)."""
    paths = [videos.find(vid_id) for vid_id in ids.split(",")]
    if not paths or None in paths:
        raise HTTPException(404, "Some of those videos aren't here any more.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:  # MP4s are already compressed
        for path in paths:
            zf.write(path, _file_name(path))
    if videos.folder_name(name):
        zip_name = f"{videos.folder_name(name)}.zip"
    else:
        who = {_file_name(p).rsplit("-", 1)[0] for p in paths}
        zip_name = f"{who.pop() if len(who) == 1 else 'movieai'}-{len(paths)}-videos.zip"
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


def _split_words(template: str) -> tuple[str, str]:
    """A theme's "best quality, {prompt}, full body" -> the words before and
    after your prompt."""
    before, _, after = template.partition("{prompt}")
    return before.strip(" ,"), after.strip(" ,")


@app.get("/api/videos/{vid_id}/recipe")
def video_recipe(vid_id: str) -> dict:
    """Library → Copy settings: everything to make this video again on the
    Custom tab (a new seed each time). Videos made before the full
    settings were saved fill the gaps from their theme as it is now
    ("complete": false)."""
    info = videos.info(vid_id)
    if info is None:
        raise HTTPException(404, "That video isn't here any more.")
    start = settings.get()["custom"]
    theme = themes.get(info.get("theme", "")) or {}
    template = info.get("words") or theme.get("prompt") or _prompt_template(start["prompt_before"], start["prompt_after"])
    before, after = _split_words(template)
    width, height = info.get("size") or [theme.get("width", start["width"]), theme.get("height", start["height"])]
    frames = info.get("frames", theme.get("frames", start["frames"]))
    pick = lambda key: info.get(key, theme.get(key, start[key]))  # noqa: E731
    return {
        "prompt": info.get("prompt", ""),
        "character": info.get("character", ""),
        "complete": all(key in info for key in ("words", "negative", "guidance", "scheduler")),
        "custom": {
            "model": info.get("model") or theme.get("model", ""),
            "loras": info.get("loras", theme.get("loras", [])),
            "prompt_before": before,
            "prompt_after": after,
            "negative": pick("negative"),
            "width": width,
            "height": height,
            "frames": frames,
            "fps": pick("fps"),
            "steps": pick("steps"),
            "guidance": pick("guidance"),
            "scheduler": pick("scheduler"),
        },
    }


class DeleteRequest(BaseModel):
    ids: list[str]


@app.post("/api/videos-delete")
def delete_videos(req: DeleteRequest) -> dict:
    """Library → Select → Delete: saved videos, gone for good (the page
    asks "are you sure" first)."""
    if not req.ids or len(req.ids) > 1000:
        raise HTTPException(400, "Pick some videos first.")
    return {"deleted": videos.delete_saved(req.ids)}


class SaveRequest(BaseModel):
    character: str


@app.post("/api/videos/{vid_id}/save")
def save_video(vid_id: str, req: SaveRequest) -> dict:
    character = " ".join(req.character.split())
    if not videos.folder_name(character):
        raise HTTPException(400, "Type a character name to save.")
    try:
        videos.save_to_character(vid_id, character)
    except FileNotFoundError:
        raise HTTPException(404, "That video isn't here any more.")
    return {"status": "saved", "character": character}


@app.get("/api/status")
def status() -> dict:
    """For the line at the top of the page: the graphics card and its memory,
    and how many video jobs are being made or waiting."""
    return {"gpu": gpu.status(), "queue": jobs.queue()}


class SettingsRequest(BaseModel):
    use_3060_settings: bool


DEVICE_NAMES = {
    "cuda": "NVIDIA graphics card (CUDA)",
    "mps": "Apple graphics (MPS)",
    "cpu": "the processor (very slow for video)",
    "none": "nothing yet (the video packages aren't installed)",
}


@app.get("/api/settings")
def get_settings() -> dict:
    device = settings.device()
    return {
        "use_3060_settings": settings.get()["use_3060_settings"],
        "device": device,
        "device_name": DEVICE_NAMES.get(device, device),
        "max_videos": settings.get()["max_videos"],
    }


@app.post("/api/settings")
def change_settings(req: SettingsRequest) -> dict:
    settings.set_local("use_3060_settings", req.use_3060_settings)
    return get_settings()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    for name in ("app.css", "js/main.js"):
        html = html.replace(f'"{name}"', f'"{name}?v={STARTED}"')
    return html


# Must come last: anything not under /api is a file from web/.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
