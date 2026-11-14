"""The web server: serves the page in web/ and a small JSON API under /api."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import generation
from .themes import THEMES

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="ImageAi")


class GenerateRequest(BaseModel):
    theme: str
    prompt: str


@app.get("/api/themes")
def list_themes() -> list[dict]:
    return THEMES


@app.post("/api/generate")
def generate(req: GenerateRequest) -> dict:
    return generation.generate(theme=req.theme, prompt=req.prompt)


# Must come last: anything not under /api is a file from web/.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
