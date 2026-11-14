# ImageAi

A website for making pictures for games: pick a theme, type a prompt, get an
image back. Built in small phases; each phase should leave something that
runs. Start it with `python3 start.py` (see README.md).

## Who it's for

- One user, often on a phone. Mostly game character art.
- Plain, simple language in the page, in messages and in explanations.
- Runs on Linux now (RTX 3060, 12 GB). Moves to a Mac Studio (Apple Silicon)
  later and is reached over Tailscale.

## Ground rules

- **Phone first.** Every screen must work at phone width (375px). Big tap
  targets, 16px inputs (stops iPhone zoom). Check desktop width too.
- **Image work on the server, in Python.** Resizing, cropping, pixel work,
  everything. The browser only shows pictures and sends requests.
- **No browser pop-ups.** No `confirm()`, `alert()` or `prompt()`; a blocked
  pop-up silently answers No. Ask and tell inside the page.
- **Cross-platform.** Nothing Linux-only: use `pathlib`, no shell scripts
  needed to run it, no hard-coded `/home/...` paths. Pick the device in code
  (`cuda`, then `mps`, then `cpu`), never assume CUDA.
- **Listen on the network** (`0.0.0.0`) so the phone can reach it. Port is
  set with `--port` or `IMAGEAI_PORT`.
- **Keep it lean.** The last project grew lots of unused parts. Add only what
  the current phase needs; delete experiments that didn't pan out.
- **Big files never go in git:** models, LoRAs, generated pictures.

## How it's built

- **Server:** FastAPI + uvicorn (`server/`). Page routes are static files;
  everything else is JSON under `/api/`.
- **Page:** plain HTML, CSS and JavaScript (`web/`). No framework, no npm,
  no build step: edit a file, reload the page. When `app.js` grows past a
  few hundred lines, split it into ES modules under `web/js/`
  (`<script type="module">`). Revisit a framework only if the page gets
  truly complex (many screens with shared state); if so, prefer one that
  needs no build step (e.g. Preact + htm loaded as a vendored file).
- **Generation** plugs in at `server/generation.py` and nowhere else in the
  web code. Routes call it; it returns plain data.
- Long jobs never block a request: the server queues them and the page asks
  for progress.

## Layout

```
start.py            sets up .venv, then runs the server
server/app.py       routes
server/themes.py    theme list (moves to themes/*.json in phase 1)
server/generation.py  where image making plugs in
web/                index.html, app.css, app.js
```

## Plan

Each phase is a small story. Finish, check at phone and desktop width,
commit, then move on.

- [x] **Phase 0 — Shell.** Page with theme picker, prompt, Generate button,
  empty result. Generate says "Not connected yet".
- [ ] **Phase 1 — Themes as files.** Each theme is a JSON file in `themes/`
  (name, hint, later: model, LoRAs, prompt wording, size). Server reads the
  folder; adding a theme needs no code change. Remember the last theme and
  prompt on the phone (localStorage).
- [ ] **Phase 2 — Jobs with a fake generator.** Generate creates a job; the
  server makes a placeholder picture with Pillow (prompt text on a coloured
  card) after a short delay. Page shows "waiting / working / done", then the
  picture. Pictures saved to `outputs/` with their settings beside them.
  This builds the whole flow before any AI is involved.
- [ ] **Phase 3 — First real model.** One model via `diffusers` (likely an
  SDXL / Illustrious checkpoint for character art). Device picked
  automatically (CUDA here, MPS on the Mac). Model path in settings, not in
  code. Model stays loaded between pictures. Real progress steps.
- [ ] **Phase 4 — Themes drive the model.** A theme picks its checkpoint,
  LoRAs, extra prompt words, negative prompt and picture size.
- [ ] **Phase 5 — Library.** Browse past pictures, see their prompt and
  theme, make again, delete (with an in-page "are you sure").
- [ ] **Phase 6 — Mac Studio + Tailscale.** Move to the Mac, check MPS speed,
  reach it from the phone over Tailscale. Consider a simple password if it's
  ever reachable from outside the tailnet.

Later ideas (not planned yet): more models (e.g. Qwen-Image / Qwen-Image-Edit),
edit modes (redraw / paint over), training the user's own LoRAs, game
sprites and animation frames.

## Checking work

- Start: `python3 start.py` (or `--port` if 8100 is busy).
- Look at the page in the browser at phone width (375px) and desktop width;
  the console must stay clean.
- Don't commit unless asked.
