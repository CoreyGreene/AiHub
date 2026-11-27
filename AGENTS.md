# AGENTS.md

A short guide for AI coding helpers (and people) working on AiHub.

## What it is

One website for all the local AI tools, built for one person, used from a Mac or a phone. The front page has a
tile per tool; opening a tile starts that tool (if it isn't running) and shows its own pages, unchanged. A bar at
the top of every page shows which tools are running, how much memory each uses, and a Stop button. No login.

| Tool | Folder | What it does |
|---|---|---|
| Image AI | `apps/image` | Pictures from a prompt: themes, library, workflows (SDXL, FLUX.2 klein, Qwen-Image) |
| 3D AI | `apps/3d` | Pictures into textured 3D models with TRELLIS.2 (items and props) |
| Code AI | `apps/code` | Ask the local language models; bulk runs, pipelines; an MCP connector for Claude |
| Movie AI | `apps/movie` | Short videos with sound (LTX-2.5 on the Mac; Wan), from a prompt or a start picture |
| Talk | `apps/talk` | Talk with your local AI: it hears (Whisper), thinks (Code AI's model), does things and answers out loud; Always listening for a wake word on the Mac. Also the 🎤 buttons' hearing |
| Lights AI | `apps/lights` | The HALO Home lights over Bluetooth: on, off, brightness, warm/cool, per light, group or all; Talk uses it |

Each tool came from its own repo, history and all (`git subtree`), and keeps its own `AGENTS.md` and `README.md`.

## Run it

```bash
python3 start.py            # makes .venv, installs the hub's requirements, starts on port 8000
```

Then open `http://localhost:8000` (or the Mac's address from a phone). The tools start when their tile is opened.
Ctrl+C stops the hub and every tool it started.

## How it's built

- **Hub:** FastAPI + uvicorn in `hub/`; its pages are plain HTML, CSS and JS in `hub/web/` (no framework, no build).
- **Each tool runs as its own program**, with its own `start.py` and `.venv`: their Python packages clash (PyTorch,
  MLX, TRELLIS), so they can't share one. `hub/apps.py` starts a tool with
  `python3 start.py --host 127.0.0.1 --port <its port>` in its own process group (Stop ends everything it started:
  model servers, the TRELLIS worker), and reads its memory (the whole process tree's footprint, the number Activity
  Monitor shows).
- **Pass-through:** `hub/app.py` sends `/<tool id>/…` to the tool's port and passes the answer back, streaming.
  Tool pages use relative links only, so they work under `/<tool id>/` unchanged. HTML pages get
  `<script src="/hub/bar.js">` added before `</body>`: the bar (`hub/web/bar.js`, self-contained, `aihub-` names).
  Opening a stopped tool's page starts it and shows `waiting.html`; its API calls answer 503 until it runs (so a
  page left open doesn't restart a tool you stopped).
- **A tool that isn't set up** (no `.venv`) shows "Not set up yet". The hub never makes a tool's `.venv` itself:
  some need several GB of downloads (PyTorch), done by hand once.
- **Models:** `models_dir` in `hub/settings.json` (this machine's in `hub/settings.local.json`) holds one folder per
  kind; each tool's `models` names its folder. The hub gives a tool `AIHUB_MODELS_DIR` (that folder) when it starts
  it: Image AI and Movie AI use it as `models_dir`; Code AI looks for models given by folder name there; 3D AI's
  models are named in `trellis-mac/local-model/pipeline.json` (TRELLIS's own file, outside this repo). The nudity
  checkers are in one shared folder, `safety_models` in `hub/settings.json` (`SafetyModels`); the hub gives every tool
  `AIHUB_SAFETY_DIR`, and Image AI and Movie AI load their checkers from it.
- **Making room:** Talk keeps Code AI's Gemma loaded while it runs; Code AI runs it beside its working model when
  both fit with `headroom_gb` (16) free. Before Image, Movie, 3D or Sound AI load a model, they call
  `POST /hub/api/make-room` (`aihub_room.py` in each); only if it won't fit does Code AI let go of models it isn't
  using (Gemma last).
- **Connector:** `connector/aihub_mcp.py` is an MCP server (stdio, standard library only) that gives Claude
  Image AI and 3D AI tools: themes, make, workflows, Staging, save pictures, approve; 3D make, bulk, status,
  models. It calls the hub's pass-through (`/image/…`, `/3d/…`) and starts a stopped tool through the hub.
  Code AI keeps its own connector (`apps/code/connector`). Register it in Claude's MCP settings with the
  hub's `.venv/bin/python` and the script's full path.
- **Mic buttons:** `bar.js` adds a 🎤 under every `<textarea>` (also ones added later) when the page is a secure
  context (https or localhost). The recording goes to `/hub/api/listen`, which starts Talk if needed and passes it
  on; the words are added to the box.
- **Autostart:** `autostart` in `hub/settings.local.json` lists tools started with the hub (Talk adds itself while
  Always listening is on: `POST /hub/api/apps/{id}/autostart`). Tools are told the hub's address (`AIHUB_URL`).
- **Settings:** `hub/settings.json` (shared: tiles, ports, models folders) + `hub/settings.local.json` (this machine).

## Rules

- **Phone first.** Every screen works at 375 px; big tap targets; 16 px inputs.
- **No browser pop-ups.** Ask inside the page (two-tap Stop).
- **Plain, simple words** in the pages and their messages.
- **Keep it lean.** Only what's needed.
- **Nothing private or big in git:** no models, pictures, GLBs, themes, logs, `*.local.json` or personal paths
  (each tool's `.gitignore` covers its own). Check `git status` before committing; commit only when the user says so.
