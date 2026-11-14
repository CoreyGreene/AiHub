"""The web server: serves the page in web/ and a small JSON API under /api."""

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import generation, pictures
from .themes import THEMES

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


@app.get("/api/themes")
def list_themes() -> list[dict]:
    return THEMES


@app.post("/api/generate")
def generate(req: GenerateRequest) -> dict:
    made = generation.generate(theme=req.theme, prompt=req.prompt)
    pic_id = pictures.keep_new(made, theme=req.theme, prompt=req.prompt)
    return {"status": "done", "id": pic_id, "image": f"api/pictures/{pic_id}"}


@app.get("/api/pictures/{pic_id}")
def picture(pic_id: str, download: bool = False) -> FileResponse:
    path = pictures.find(pic_id)
    if path is None:
        raise HTTPException(404, "That picture isn't here any more.")
    # download=1 makes the browser save the file instead of showing it.
    name = None
    if download:
        who = path.parent.name if path.parent.parent == pictures.CHARACTERS else "imageai"
        name = f"{who}-{pic_id[:8]}.png"
    return FileResponse(path, media_type="image/png", filename=name)


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


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    for name in ("app.css", "app.js"):
        html = html.replace(f'"{name}"', f'"{name}?v={STARTED}"')
    return html


# Must come last: anything not under /api is a file from web/.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
