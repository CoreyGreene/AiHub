# ImageAi

A website for making pictures for games: pick a theme, type a prompt, get an
image back. Built in small phases; each phase should leave something that
runs. Start it with `python3 start.py` (see README.md).

## Who it's for

- One user, often on a phone. Mostly game character art.
- Plain, simple language in the page, in messages and in explanations.
- Runs on Linux now (RTX 3060, 12 GB) — only for building the website.
- **The real home is a Mac Studio** (Apple M5, 128 GB shared memory), reached
  from the phone over Tailscale. That machine decides which models we use:
  - 128 GB shared between CPU and GPU means big models (e.g. Qwen-Image,
    ~20B) fit whole, and several can stay loaded at once. The tricks the 3060
    needed (CPU offloading, heavy quantization, swapping models in and out)
    shouldn't be needed there.
  - Besides PyTorch on the Mac GPU (MPS), Apple-native options are on the
    table: MLX-based image models and Core ML models. These are often faster
    on Apple Silicon than the PyTorch versions. Pick per model by testing on
    the Mac, not by guessing.
  - Speed and what fits must be measured on the Mac Studio itself; the 3060
    is not a guide.

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

## Public repo

The GitHub repo (github.com/CoreyGreene/ImageAi) is **public**. Anything
committed can be seen by anyone, and stays in the history even if deleted
later. So:

- **Never in git:** AI models of any kind (checkpoints, LoRAs, embeddings,
  VAEs, MLX and Core ML models), and pictures of any kind (generated ones,
  training sets, reference art). `.gitignore` covers these; the only
  pictures allowed are the page's own icons under `web/`.
- **Nothing private:** no passwords, API keys or tokens, no Tailscale
  addresses or machine names, no personal paths (`/home/...`,
  `/Users/...`), no email addresses.
- **Local settings stay local.** Where models live on disk and anything
  machine-specific go in an ignored file (`.env` or `*.local.json`).
  Commit an example file with made-up values instead.
- **Themes are shared, models are not.** A theme file may name a model or
  LoRA (and where to download it), but never includes the file itself or
  a private path to it.
- **Before every commit**, run `git status` and look at the list. If a big
  file or a private value shows up, stop and fix `.gitignore` first.

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
  web code. Routes call it; it returns plain data. Behind it, each way of
  running a model (diffusers/PyTorch, MLX, Core ML) is its own small
  "backend" with the same shape, so a theme can name its backend and the
  website never cares which one ran.
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
  SDXL / Illustrious checkpoint for character art: small enough to also
  test on the 3060). Device picked automatically (CUDA here, MPS on the
  Mac). Model path in settings, not in code. Model stays loaded between
  pictures. Real progress steps.
- [ ] **Phase 4 — Themes drive the model.** A theme picks its backend,
  model, LoRAs, extra prompt words, negative prompt and picture size.
- [ ] **Phase 5 — Library.** Browse past pictures, see their prompt and
  theme, make again, delete (with an in-page "are you sure").
- [ ] **Phase 6 — Mac Studio + Tailscale.** Move to the Mac, reach it from
  the phone over Tailscale. Time the phase 3 model on MPS. Consider a simple
  password if it's ever reachable from outside the tailnet.
- [ ] **Phase 7 — Big and Mac-native models.** On the Mac only: bigger models
  that didn't fit the 3060 (e.g. Qwen-Image / Qwen-Image-Edit), and MLX or
  Core ML versions where they're faster. Compare the same prompt across
  backends before choosing.

Later ideas (not planned yet): edit modes (redraw / paint over), training
the user's own LoRAs (the Mac's memory makes this realistic), game sprites
and animation frames.

## Checking work

- Start: `python3 start.py` (or `--port` if 8100 is busy).
- Look at the page in the browser at phone width (375px) and desktop width;
  the console must stay clean.
- Don't commit unless asked.
