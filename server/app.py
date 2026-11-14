"""The web server: serves the page in web/ and a small JSON API under /api."""

import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import generation
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
    return generation.generate(theme=req.theme, prompt=req.prompt)


@app.get("/api/demo-image")
def demo_image(download: bool = False) -> FileResponse:
    # download=1 makes the browser save the file instead of showing it.
    name = "imageai-demo.png" if download else None
    return FileResponse(generation.DEMO_IMAGE, media_type="image/png", filename=name)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    for name in ("app.css", "app.js"):
        html = html.replace(f'"{name}"', f'"{name}?v={STARTED}"')
    return html


# Must come last: anything not under /api is a file from web/.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
