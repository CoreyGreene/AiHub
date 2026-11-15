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

from . import generation, gpu, jobs, lock, pictures, settings, themes, uploads, workflows

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
# Changes on every server start. The page asks for app.css and app.js with
# it attached, so a restart always gets fresh files, never old cached ones.
STARTED = str(int(time.time()))

app = FastAPI(title="ImageAi")


@app.middleware("http")
async def code_lock(request, call_next):
    # With the lock on, a browser without the code's cookie sees only the
    # lock page; everything else (pictures too) is turned away.
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
    """Where the Custom tab starts: model, words and picture settings."""
    start = dict(settings.get()["custom"])
    models = generation.choices()["models"]
    if start["model"] not in models:
        start["model"] = models[0] if models else ""
    return {k: v for k, v in start.items() if k not in ("backend", "model_config")}


class LoraChoice(BaseModel):
    file: str
    weight: float


class CustomChoice(BaseModel):
    """The Custom tab: your own theme for these pictures (no theme file)."""
    model: str
    loras: list[LoraChoice] = []
    prompt_before: str = ""
    prompt_after: str = ""
    negative: str = ""
    width: int
    height: int
    steps: int
    guidance: float
    scheduler: str


class ThemeWords(BaseModel):
    """The Advanced tab: the theme's words, changed for these pictures only."""
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


def _check_picture_settings(req, found: dict) -> None:
    """Size, steps, guidance and sampler (a theme change or a custom picture)."""
    for label, value in (("Width", req.width), ("Height", req.height)):
        if not 512 <= value <= 2048 or value % 8:
            raise HTTPException(400, f"{label} must be 512 to 2048, and divide by 8.")
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
    steps: int
    guidance: float
    scheduler: str


def _theme_keys(req: ThemeChange) -> dict:
    """The theme file's keys from the Theme tab's form, once checked."""
    name = " ".join(req.name.split())
    if not name:
        raise HTTPException(400, "Give the theme a name.")
    found = _check_model_and_loras(req.model, req.loras)
    _check_picture_settings(req, found)
    return {
        "name": name,
        "hint": " ".join(req.hint.split()),
        "prompt": _prompt_template(req.prompt_before, req.prompt_after),
        "negative": _tidy(req.negative),
        "model": req.model,
        "loras": [{"file": l.file, "weight": l.weight} for l in req.loras],
        "width": req.width,
        "height": req.height,
        "steps": req.steps,
        "guidance": req.guidance,
        "scheduler": req.scheduler,
    }


@app.put("/api/themes/{theme_id}")
def change_theme(theme_id: str, req: ThemeChange) -> dict:
    """Save changes to a theme file. The next picture uses them."""
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
    (bad name, already there, no room) is told at once, not after 7 GB."""
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


def _job_parts(req: GenerateRequest) -> tuple[str, dict, str]:
    """Check what Generate (or a workflow item) was given; returns
    (theme id, the theme to use, the prompt). Raises 400 if something's off."""
    theme_id = "custom" if req.custom else req.theme
    theme = None if req.custom else themes.get(req.theme)
    if theme is None and not req.custom:
        raise HTTPException(400, "That theme isn't there any more. Reload the page.")
    prompt = " ".join(req.prompt.split())
    if not prompt:
        raise HTTPException(400, "Type a prompt first.")
    most = settings.get()["max_pictures"]
    if not 1 <= req.count <= most:
        raise HTTPException(400, f"Pick between 1 and {most} pictures.")
    if req.custom:
        # Your own theme, made from the Custom tab (nothing is saved to a file).
        c = req.custom
        _check_picture_settings(c, _check_model_and_loras(c.model, c.loras))
        start = settings.get()["custom"]
        theme = {
            "name": "Custom",
            "backend": start["backend"],
            "model_config": start["model_config"],
            "model": c.model,
            "loras": [{"file": l.file, "weight": l.weight} for l in c.loras],
            "prompt": _prompt_template(c.prompt_before, c.prompt_after),
            "negative": _tidy(c.negative),
            **{key: getattr(c, key) for key in ("width", "height", "steps", "guidance", "scheduler")},
        }
    elif req.words:
        # The theme's words as changed on the Advanced tab (the file stays as it is).
        w = req.words
        theme = {**theme, "prompt": _prompt_template(w.prompt_before, w.prompt_after), "negative": _tidy(w.negative)}
    return theme_id, theme, prompt


@app.post("/api/generate")
def generate(req: GenerateRequest) -> dict:
    """Adds a picture to the queue; the page then asks /api/jobs/{job} for progress."""
    theme_id, theme, prompt = _job_parts(req)
    try:
        return {"job": jobs.submit(theme_id, theme, prompt, req.count)}
    except jobs.QueueFull as err:
        raise HTTPException(429, str(err))


# --- Workflows: saved lists of items, each like one Advanced / Custom Generate ---


class WorkflowItem(GenerateRequest):
    name: str = ""  # where its pictures go in staging (empty: the workflow's name + a number)


class WorkflowName(BaseModel):
    name: str


class Workflow(BaseModel):
    name: str
    items: list[WorkflowItem] = []


def _flow_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise HTTPException(400, "Give the workflow a name.")
    return name


@app.get("/api/workflows")
def workflow_list() -> list[dict]:
    return workflows.listing()


@app.get("/api/workflows/{flow_id}")
def workflow_get(flow_id: str) -> dict:
    """The workflow, and how its last Start is going (one per item)."""
    flow = workflows.get(flow_id)
    if flow is None:
        raise HTTPException(404, "That workflow isn't there any more.")
    return {**flow, "running": workflows.is_running(flow_id), "run": workflows.run_status(flow_id)}


RUNNING = "This workflow is running. Change it when it's done."


@app.post("/api/workflows")
def workflow_new(req: WorkflowName) -> dict:
    return {"id": workflows.create(_flow_name(req.name))}


@app.put("/api/workflows/{flow_id}")
def workflow_save(flow_id: str, req: Workflow) -> dict:
    """Save the whole workflow: its name and every item, each checked like Generate."""
    if workflows.get(flow_id) is None:
        raise HTTPException(404, "That workflow isn't there any more.")
    if workflows.is_running(flow_id):
        raise HTTPException(409, RUNNING)
    items = []
    for n, item in enumerate(req.items, 1):
        try:
            _job_parts(item)
        except HTTPException as err:
            raise HTTPException(400, f"Item {n}: {err.detail}")
        items.append({**item.model_dump(exclude_none=True), "name": " ".join(item.name.split()), "prompt": " ".join(item.prompt.split())})
    workflows.save(flow_id, {"name": _flow_name(req.name), "items": items})
    return {"status": "saved"}


@app.post("/api/workflows/{flow_id}/start")
def workflow_start(flow_id: str) -> dict:
    """Queue every item; their pictures go to Library → Staging."""
    flow = workflows.get(flow_id)
    if flow is None:
        raise HTTPException(404, "That workflow isn't there any more.")
    if not flow["items"]:
        raise HTTPException(400, "Add an item first.")
    if workflows.is_running(flow_id):
        raise HTTPException(409, "This workflow is already running.")
    parts = []
    for n, item in enumerate(flow["items"], 1):
        try:
            theme_id, theme, prompt = _job_parts(WorkflowItem(**item))
        except HTTPException as err:
            raise HTTPException(400, f"Item {n}: {err.detail}")
        parts.append((theme_id, theme, prompt, item["count"]))
    if len(parts) > jobs.room():
        raise HTTPException(429, "The queue is too full for this workflow. Try again when some jobs are done.")
    workflows.start(flow_id, parts)
    return {"status": "started"}


@app.delete("/api/workflows/{flow_id}")
def workflow_delete(flow_id: str) -> dict:
    if workflows.is_running(flow_id):
        raise HTTPException(409, RUNNING)
    if not workflows.delete(flow_id):
        raise HTTPException(404, "That workflow isn't there any more.")
    return {"status": "deleted"}


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    found = jobs.status(job_id)
    if found is None:
        raise HTTPException(404, "That picture job isn't known (the server may have restarted).")
    return found


@app.get("/api/queue")
def queue_list() -> list[dict]:
    """Every picture job being made or waiting, in order."""
    return jobs.listing()


@app.delete("/api/queue/{job_id}")
def queue_remove(job_id: str) -> dict:
    if not jobs.remove(job_id):
        raise HTTPException(404, "That job isn't in the queue any more.")
    return {"status": "removed"}


@app.get("/api/characters")
def characters() -> list[dict]:
    return pictures.list_characters()


def _with_theme_names(found: dict) -> dict:
    """Show the theme's name where it still exists, else its id."""
    names = {t["id"]: t["name"] for t in themes.public_list()} | {"custom": "Custom"}
    for pic in found["pictures"]:
        pic["theme"] = names.get(pic["theme"], pic["theme"])
    return found


@app.get("/api/characters/{folder}")
def character(folder: str) -> dict:
    found = pictures.character(folder)
    if found is None:
        raise HTTPException(404, "That character isn't in the library.")
    return _with_theme_names(found)


# --- Staging: workflow pictures waiting to be picked ---


@app.get("/api/staging")
def staging_list() -> list[dict]:
    return pictures.list_characters("staging")


@app.get("/api/staging/{folder}")
def staging_group(folder: str) -> dict:
    found = pictures.character(folder, "staging")
    if found is None:
        raise HTTPException(404, "That group isn't in staging any more.")
    return _with_theme_names(found)


class ApproveRequest(BaseModel):
    ids: list[str]
    character: str


@app.post("/api/staging/approve")
def staging_approve(req: ApproveRequest) -> dict:
    """Move the chosen staging pictures to a character (new or existing)."""
    character = " ".join(req.character.split())
    if not pictures.folder_name(character):
        raise HTTPException(400, "Type a character name (letters or numbers).")
    moved = 0
    for pic_id in req.ids:
        path = pictures.find(pic_id)
        if path is not None and pictures.is_staged(path):
            pictures.save_to_character(pic_id, character)
            moved += 1
    return {"moved": moved, "folder": pictures.folder_name(character)}


@app.get("/api/pictures/{pic_id}")
def picture(pic_id: str, download: bool = False) -> FileResponse:
    path = pictures.find(pic_id)
    if path is None:
        raise HTTPException(404, "That picture isn't here any more.")
    # download=1 makes the browser save the file instead of showing it.
    return FileResponse(path, media_type="image/png", filename=_file_name(path) if download else None)


def _file_name(path: Path) -> str:
    who = path.parent.name if pictures.is_saved(path) else "imageai"
    return f"{who}-{path.stem[:8]}.png"


@app.get("/api/pictures-zip")
def pictures_zip(ids: str, name: str = "") -> Response:
    """Several pictures in one zip file, named after the character if one
    was typed (e.g. grim-the-goblin.zip)."""
    paths = [pictures.find(pic_id) for pic_id in ids.split(",")]
    if not paths or None in paths:
        raise HTTPException(404, "Some of those pictures aren't here any more.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:  # PNGs are already compressed
        for path in paths:
            zf.write(path, _file_name(path))
    if pictures.folder_name(name):
        zip_name = f"{pictures.folder_name(name)}.zip"
    else:
        who = {_file_name(p).rsplit("-", 1)[0] for p in paths}
        zip_name = f"{who.pop() if len(who) == 1 else 'imageai'}-{len(paths)}-pictures.zip"
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


@app.get("/api/pictures/{pic_id}/recipe")
def picture_recipe(pic_id: str) -> dict:
    """Library → Copy settings: everything to make this picture again (a
    new seed each time). "theme" is its theme's id when that theme is still
    there (the page opens Advanced with it, and the picture's words when
    saved); otherwise "" and the page uses "custom" on the Custom tab.
    Pictures made before the full settings were saved fill the gaps from
    their theme as it is now ("complete": false)."""
    info = pictures.info(pic_id)
    if info is None:
        raise HTTPException(404, "That picture isn't here any more.")
    start = settings.get()["custom"]
    theme = themes.get(info.get("theme", "")) or {}
    template = info.get("words") or theme.get("prompt") or _prompt_template(start["prompt_before"], start["prompt_after"])
    before, after = _split_words(template)
    width, height = info.get("size") or [theme.get("width", start["width"]), theme.get("height", start["height"])]
    pick = lambda key: info.get(key, theme.get(key, start[key]))  # noqa: E731
    saved_words = "words" in info and "negative" in info
    return {
        "theme": info.get("theme", "") if theme else "",
        "words": {"prompt_before": before, "prompt_after": after, "negative": info["negative"]} if saved_words else None,
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
            "steps": pick("steps"),
            "guidance": pick("guidance"),
            "scheduler": pick("scheduler"),
        },
    }


class EditRequest(BaseModel):
    prompt: str


@app.post("/api/pictures/{pic_id}/edit")
def edit_picture(pic_id: str, req: EditRequest) -> dict:
    """The Edit button: change this picture by an instruction. Queued like
    any picture; follow it at /api/jobs/{job}."""
    instruction = " ".join(req.prompt.split())
    if not instruction:
        raise HTTPException(400, "Type what to change first.")
    if pictures.find(pic_id) is None:
        raise HTTPException(404, "That picture isn't here any more.")
    try:
        return {"job": jobs.submit_edit(pic_id, instruction)}
    except jobs.QueueFull as err:
        raise HTTPException(429, str(err))


class DeleteRequest(BaseModel):
    ids: list[str]


@app.post("/api/pictures-delete")
def delete_pictures(req: DeleteRequest) -> dict:
    """Library → Select → Delete: saved pictures, gone for good (the page
    asks "are you sure" first)."""
    if not req.ids or len(req.ids) > 1000:
        raise HTTPException(400, "Pick some pictures first.")
    return {"deleted": pictures.delete_saved(req.ids)}


class SaveRequest(BaseModel):
    character: str


@app.post("/api/pictures/{pic_id}/save")
def save_picture(pic_id: str, req: SaveRequest) -> dict:
    character = " ".join(req.character.split())
    if not pictures.folder_name(character):
        raise HTTPException(400, "Type a character name to save.")
    try:
        pictures.save_to_character(pic_id, character)
    except FileNotFoundError:
        raise HTTPException(404, "That picture isn't here any more.")
    return {"status": "saved", "character": character}


@app.get("/api/status")
def status() -> dict:
    """For the line at the top of the page: the graphics card and its memory,
    and how many picture jobs are being made or waiting."""
    return {"gpu": gpu.status(), "queue": jobs.queue()}


class SettingsRequest(BaseModel):
    use_3060_settings: bool


DEVICE_NAMES = {"cuda": "NVIDIA graphics card (CUDA)", "mps": "Apple graphics (MPS)", "cpu": "the processor (slow)"}


@app.get("/api/settings")
def get_settings() -> dict:
    device = settings.device()
    return {
        "use_3060_settings": settings.get()["use_3060_settings"],
        "device": device,
        "device_name": DEVICE_NAMES.get(device, device),
        "max_pictures": settings.get()["max_pictures"],
        "page_size": settings.get()["page_size"],
        "thumbs_page_size": settings.get()["thumbs_page_size"],
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
