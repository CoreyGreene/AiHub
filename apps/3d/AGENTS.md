# AGENTS.md

A short guide for AI coding helpers (and people) working on MeshAi.

## What it is

A small website for turning 2D pictures into 3D models (GLB) for the game:
give it a picture (or a whole folder of them), it makes textured 3D models with
**TRELLIS.2**, keeps them in a library with several versions each, and shows
them in a 3D viewer. Sister of `../Image-Ai` (pictures, port 8100) and
`../Code-Ai` (port 8200); same look, same rules. Built 2026-11-23.

Use: **items and props** (pictures from Image-Ai's "Becky Item Style" theme).
Characters are made with Meshy instead (the user's choice: TRELLIS's faces and
colours aren't good enough for them).

## Run it

```bash
python3 start.py            # makes .venv, installs requirements, starts on port 8300
python3 start.py --port 9000
```

Needs `../trellis-mac` set up first (its own `.venv`, the Metal texture tools and
`local-model/`): see `../trellis-mac/CLAUDE.md`. The settings `trellis_dir` points there.

## How it's built

- **Server:** FastAPI + uvicorn in `server/`. Page: plain HTML, CSS and ES modules in
  `web/` (no framework, no build step). 3D viewer: Google's `<model-viewer>` web
  component, one file in `web/vendor/` (Apache-2.0, licence beside it).
- **TRELLIS runs in its own Python** (its packages clash with ours):
  `server/trellis.py` starts `server/trellis_worker.py` with `trellis-mac/.venv/bin/python`
  and keeps it running, so the model (~18 GB, ~1 min to load) loads once. Jobs go in as
  JSON lines on stdin; answers come back on stdout lines starting `@@MESHAI ` (anything
  else is TRELLIS talking → `logs/trellis.log`). Let go after `idle_minutes`.
  The worker copies trellis-mac's `generate.py` Metal bake path (pre-simplify to
  200k faces → `o_voxel.postprocess.to_glb` → GLB with 1024 px PBR textures, Y-up).
- **Queue** (`server/jobs.py`): one job = one version; one at a time; waiting jobs can be
  removed, the working one stopped (that stops the worker; the next job reloads it).
- **Library** (`server/library.py`): `library/<slug>/model.json` + `pictures/` + `<version>.glb`.
  Same name → more versions of the same model. Served under `/files/<slug>/…`.
- **Bulk:** `/api/browse` shows folders inside the allowed ones (settings `folders`,
  set per machine in `settings.local.json`); `/api/bulk` makes a model per picture,
  named from the file name, skipping names already in the library.
- **Settings:** `server/settings.json` (shared) + `server/settings.local.json` (this machine).

## Rules

- **Phone first.** Every screen works at 375 px; big tap targets; 16 px inputs.
- **No browser pop-ups.** Ask inside the page (two-tap delete buttons).
- **Plain, simple words** in the page and its messages.
- **Keep it lean.** Only what's needed.
- **Nothing private or big in git:** no models, GLBs, pictures, `*.local.json`,
  personal paths. `.gitignore` covers them; check `git status` before committing.
  Commit only when the user says so.

## Ideas not built yet

- Make props matte (metallic 0 / roughness 1) for the cartoon look; an option per run.
- Fewer triangles for the game (decimate to a few thousand).
- Pick pictures straight from Image-Ai's library; an MCP connector like Code-Ai's.
- TRELLIS's colours come out a bit dark (suspected colour-space mix-up in the bake).
