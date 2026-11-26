"""The web server: serves the page in web/ and a small JSON API under /api.

Library files (pictures, GLBs) are served under /files/<slug>/...
"""

import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import jobs, library, settings, trellis

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="MeshAi")
library.forget_unfinished()


@app.middleware("http")
async def no_stale_page(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith(("/api/", "/files/")):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---------- status and queue ----------

@app.get("/api/status")
def status() -> dict:
    return {"problem": trellis.problem(), **jobs.summary(), "max_versions": settings.get()["max_versions"]}


@app.get("/api/jobs")
def job_list() -> list[dict]:
    return jobs.listing()


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str) -> dict:
    jobs.stop(job_id)
    return {"ok": True}


@app.post("/api/batches/{batch}/stop")
def stop_batch(batch: str) -> dict:
    return {"stopped": jobs.stop_batch(batch)}


# ---------- making ----------

def _versions(n: int) -> int:
    most = settings.get()["max_versions"]
    if not 1 <= n <= most:
        raise HTTPException(400, f"Versions: 1 to {most}.")
    return n


def _queue(slug: str, name: str, picture: str, versions: int, batch: str = "") -> list[str]:
    if why := trellis.problem():
        raise HTTPException(503, why)
    try:
        return jobs.submit(slug, name, picture, versions, batch)
    except jobs.QueueFull as err:
        raise HTTPException(429, str(err))


@app.post("/api/make")
async def make(request: Request, name: str, versions: int = 1, filename: str = "") -> dict:
    """The picture is the request body (the page sends the file as it is)."""
    picture = await request.body()
    if not picture:
        raise HTTPException(400, "Choose a picture first.")
    if len(picture) > 40 * 2**20:
        raise HTTPException(400, "That picture is too big (40 MB at most).")
    try:
        slug, file = library.add_picture(name, picture, Path(filename).suffix or ".png")
    except library.LibraryError as err:
        raise HTTPException(400, str(err))
    data = library.get(slug)
    return {"slug": slug, "jobs": _queue(slug, data["name"], file, _versions(versions))}


class More(BaseModel):
    picture: str
    versions: int = 1


@app.post("/api/models/{slug}/more")
def more(slug: str, req: More) -> dict:
    """More versions of a model, from one of its pictures."""
    data = library.get(slug)
    if data is None:
        raise HTTPException(404, "That model isn't there any more.")
    if not (library.root() / slug / "pictures" / req.picture).exists():
        raise HTTPException(400, "That picture isn't there any more.")
    return {"jobs": _queue(slug, data["name"], req.picture, _versions(req.versions))}


# ---------- library ----------

@app.get("/api/models")
def models() -> list[dict]:
    return library.listing()


@app.get("/api/models/{slug}")
def model(slug: str) -> dict:
    data = library.get(slug)
    if data is None:
        raise HTTPException(404, "That model isn't there any more.")
    return data


class Rename(BaseModel):
    name: str


@app.post("/api/models/{slug}/rename")
def rename(slug: str, req: Rename) -> dict:
    try:
        return {"slug": library.rename(slug, req.name)}
    except library.LibraryError as err:
        raise HTTPException(400, str(err))


@app.delete("/api/models/{slug}")
def delete_model(slug: str) -> dict:
    try:
        library.delete_model(slug)
    except library.LibraryError as err:
        raise HTTPException(400, str(err))
    return {"ok": True}


@app.delete("/api/models/{slug}/versions/{version}")
def delete_version(slug: str, version: str) -> dict:
    try:
        library.delete_version(slug, version)
    except library.LibraryError as err:
        raise HTTPException(400, str(err))
    return {"ok": True, "model_left": library.get(slug) is not None}


# ---------- references: models to compare others with ----------

def _references() -> list[tuple[str, Path]]:
    out = []
    for r in settings.get().get("references", []):
        path = Path(r.get("path", "")).expanduser()
        if path.suffix.lower() == ".glb" and path.is_file():
            out.append((r.get("name") or path.stem, path))
    return out


@app.get("/api/references")
def references() -> list[dict]:
    """The models to compare with (settings: references), for the model page's Compare."""
    return [{"id": i, "name": name, "url": f"references/{i}.glb"} for i, (name, _) in enumerate(_references())]


@app.get("/references/{index}.glb")
def reference_file(index: int):
    found = _references()
    if not 0 <= index < len(found):
        raise HTTPException(404)
    return FileResponse(found[index][1], media_type="model/gltf-binary")


@app.get("/files/{slug}/{rest:path}")
def files(slug: str, rest: str):
    base = (library.root() / slug).resolve()
    path = (base / rest).resolve()
    if base not in path.parents or not path.is_file() or path.name == "model.json":
        raise HTTPException(404)
    media = "model/gltf-binary" if path.suffix == ".glb" else None
    return FileResponse(path, media_type=media)


# ---------- bulk: every picture in a folder ----------

def _roots() -> list[dict]:
    out = []
    for f in settings.get().get("folders", []):
        path = Path(f["path"]).expanduser().resolve()
        if path.is_dir():
            out.append({"name": f.get("name", path.name), "path": str(path)})
    return out


def _inside(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if not path.is_dir() or not any(path == Path(r["path"]) or Path(r["path"]) in path.parents for r in _roots()):
        raise HTTPException(400, "That folder isn't inside your allowed ones (settings: folders).")
    return path


def _pictures(folder: Path) -> list[Path]:
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in library.PICTURE_TYPES
                   and not p.name.startswith(".")), key=lambda p: p.name.lower())


def _name_from_file(path: Path) -> str:
    return " ".join(path.stem.replace("_", " ").replace("-", " ").split())


@app.get("/api/browse")
def browse(path: str = "") -> dict:
    """For the folder picker: the allowed folders, or the folders inside one, with how many pictures it holds."""
    if not path:
        roots = _roots()
        return {"path": "", "name": "Your folders", "up": None, "pictures": 0,
                "folders": roots, "empty": not roots}
    folder = _inside(path)
    up = "" if any(str(folder) == r["path"] for r in _roots()) else str(folder.parent)
    subs = sorted((p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")),
                  key=lambda p: p.name.lower())
    pics = _pictures(folder)
    return {"path": str(folder), "name": folder.name, "up": up,
            "folders": [{"name": p.name, "path": str(p)} for p in subs],
            "pictures": len(pics), "sample": [p.name for p in pics[:12]]}


class Bulk(BaseModel):
    folder: str
    versions: int = 1
    skip_existing: bool = True


@app.post("/api/bulk")
def bulk(req: Bulk) -> dict:
    """A model for every picture in the folder, named after its file ("item_fridge.png" → "item fridge")."""
    folder = _inside(req.folder)
    versions = _versions(req.versions)
    pics = _pictures(folder)
    if not pics:
        raise HTTPException(400, "There are no pictures (.png, .jpg, .webp) in that folder.")
    have = {m["slug"] for m in library.listing()} if req.skip_existing else set()
    batch = uuid.uuid4().hex[:10]
    queued = skipped = 0
    for pic in pics:
        name = _name_from_file(pic) or pic.stem
        if library.slug_of(name) in have:
            skipped += 1
            continue
        slug, file = library.add_picture(name, pic.read_bytes(), pic.suffix)
        _queue(slug, library.get(slug)["name"], file, versions, batch)
        queued += 1
    return {"batch": batch, "models": queued, "skipped": skipped, "jobs": queued * versions}


# ---------- the page ----------

app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
