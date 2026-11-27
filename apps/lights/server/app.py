"""Lights AI's server.

    GET  /api/lights    every home: connected?, each light (on, brightness %, kelvin), the groups
    POST /api/set       {"lights": ["fireplace", "stair"] | "all" | "main 3", "on": true|false,
                         "brightness": 0-100, "kelvin": 2700-5000}   (any mix; names are loose)
    POST /api/refresh   ask every light how it is now
    /                   the page (web/)
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .home import Home

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
WEB = Path(__file__).resolve().parent.parent / "web"
home = Home()


@asynccontextmanager
async def lifespan(_app):
    home.start()
    yield
    await home.stop()


app = FastAPI(lifespan=lifespan)


class SetBody(BaseModel):
    lights: list[str] | str = "all"
    on: bool | None = None
    brightness: float | None = None
    kelvin: int | None = None


@app.get("/api/lights")
def lights():
    return home.view()


@app.post("/api/set")
async def set_lights(body: SetBody):
    try:
        return await home.set(body.lights, body.on, body.brightness, body.kelvin)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.post("/api/refresh")
async def refresh():
    await home.refresh()
    return {"ok": True}


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
