"""The web server: serves the page in web/ and a small JSON API under /api."""

import io
import time
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import generation, jobs, pictures, settings, themes

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
# Changes on every server start. The page asks for app.css and app.js with
# it attached, so a restart always gets fresh files, never old cached ones.
STARTED = str(int(time.time()))

app = FastAPI(title="ImageAi")


@app.middleware("http")
async def no_stale_page(request, call_next):
    # Make browsers (phones especially) check for a newer page every time,
    # so a reload always shows the latest change.
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


class GenerateRequest(BaseModel):
    theme: str
    prompt: str
    count: int = 1


@app.get("/api/themes")
def list_themes() -> list[dict]:
    return themes.public_list()


@app.get("/api/themes/details")
def theme_details() -> list[dict]:
    """Every theme in full: what it adds to the prompt, model, LoRAs, settings."""
    return [{"id": tid, **generation.describe(t)} for tid, t in themes.load().items()]


@app.post("/api/generate")
def generate(req: GenerateRequest) -> dict:
    """Adds a picture to the queue; the page then asks /api/jobs/{job} for progress."""
    theme = themes.get(req.theme)
    if theme is None:
        raise HTTPException(400, "That theme isn't there any more. Reload the page.")
    prompt = " ".join(req.prompt.split())
    if not prompt:
        raise HTTPException(400, "Type a prompt first.")
    most = settings.get()["max_pictures"]
    if not 1 <= req.count <= most:
        raise HTTPException(400, f"Pick between 1 and {most} pictures.")
    return {"job": jobs.submit(req.theme, theme, prompt, req.count)}


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    found = jobs.status(job_id)
    if found is None:
        raise HTTPException(404, "That picture job isn't known (the server may have restarted).")
    return found


@app.get("/api/characters")
def characters() -> list[dict]:
    return pictures.list_characters()


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
