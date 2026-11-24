"""The hub website: the tile page at /, and each tool's own pages at /<tool id>/.

A tool's pages are passed through unchanged, except that every page gets the
hub's bar (what's running, how much memory) added at the top. Opening a tool
that isn't running starts it; the page waits, then shows the tool.
"""

import html
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import apps

WEB = Path(__file__).resolve().parent / "web"
BAR = b'<script src="/hub/bar.js" defer></script>'
# Headers that belong to one connection, not passed along.
HOP = {"host", "connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
       "proxy-authorization", "proxy-authenticate", "accept-encoding"}

client: httpx.AsyncClient


@asynccontextmanager
async def lifespan(_app):
    global client
    client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5), follow_redirects=False)
    yield
    await client.aclose()
    apps.stop_all()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def fresh_hub_files(request: Request, call_next):
    """The hub's own files (the bar, tiles) are checked for changes every time, so an update shows at once."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/hub/"):
        response.headers["cache-control"] = "no-cache"
    return response


@app.get("/")
def tiles():
    return FileResponse(WEB / "index.html")


@app.get("/hub/api/status")
def status():
    return apps.status()


def _app_or_404(app_id: str) -> dict:
    found = apps.find(app_id)
    if not found:
        raise HTTPException(404, "There's no tool by that name.")
    return found


@app.post("/hub/api/apps/{app_id}/start")
def start(app_id: str):
    tool = _app_or_404(app_id)
    if not apps.set_up(tool):
        raise HTTPException(409, f"{tool['name']} isn't set up yet.")
    apps.start(tool)
    return {"state": apps.state(tool)}


@app.post("/hub/api/apps/{app_id}/stop")
def stop(app_id: str):
    tool = _app_or_404(app_id)
    apps.stop(tool)
    return {"state": apps.state(tool)}


app.mount("/hub", StaticFiles(directory=WEB), name="hub")


@app.api_route("/{app_id}", methods=["GET", "HEAD"])
def tool_root(app_id: str):
    _app_or_404(app_id)
    return RedirectResponse(f"/{app_id}/")  # so the tool's relative links work


@app.api_route("/{app_id}/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def tool(app_id: str, path: str, request: Request):
    tool = _app_or_404(app_id)
    wants_page = request.method == "GET" and "text/html" in request.headers.get("accept", "")
    if apps.state(tool) != "running":
        if wants_page:
            apps.start(tool)
            return _waiting_page(tool)
        return JSONResponse({"detail": f"{tool['name']} isn't running. Open its tile to start it."}, 503)

    url = f"http://127.0.0.1:{tool['port']}/{path}"
    if request.url.query:
        url += "?" + request.url.query
    headers = [(k, v) for k, v in request.headers.items() if k.lower() not in HOP]
    body = request.stream() if request.method in ("POST", "PUT", "PATCH") else None
    try:
        upstream = await client.send(
            client.build_request(request.method, url, headers=headers, content=body), stream=True)
    except httpx.ConnectError:
        if wants_page:
            apps.start(tool)
            return _waiting_page(tool)
        return JSONResponse({"detail": f"{tool['name']} stopped."}, 503)

    out_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP}
    if out_headers.get("location", "").startswith("/"):
        out_headers["location"] = f"/{app_id}" + out_headers["location"]

    if upstream.headers.get("content-type", "").startswith("text/html"):
        page = await upstream.aread()
        await upstream.aclose()
        page = _add_bar(page)
        out_headers["content-length"] = str(len(page))
        return Response(page, upstream.status_code, out_headers)
    return StreamingResponse(upstream.aiter_raw(), upstream.status_code, out_headers,
                             background=BackgroundTask(upstream.aclose))


def _add_bar(page: bytes) -> bytes:
    at = page.lower().rfind(b"</body>")
    return page[:at] + BAR + page[at:] if at >= 0 else page + BAR


def _waiting_page(tool: dict) -> HTMLResponse:
    """Shown while a tool starts: waits, then loads the tool's own page."""
    name = html.escape(tool["name"])
    page = (WEB / "waiting.html").read_text().replace("{name}", name).replace("{id}", html.escape(tool["id"]))
    return HTMLResponse(page, headers={"cache-control": "no-store"})
