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
  no build step: edit a file, reload the page. The script is ES modules
  under `web/js/` (`main.js` loads the rest). Revisit a framework only if the page gets
  truly complex (many screens with shared state); if so, prefer one that
  needs no build step (e.g. Preact + htm loaded as a vendored file).
- **Generation** plugs in at `server/generation.py` and nowhere else in the
  web code. Routes call it; it returns plain data. Behind it, each way of
  running a model (diffusers/PyTorch, MLX, Core ML) is its own small
  "backend" with the same shape, so a theme can name its backend and the
  website never cares which one ran.
- Long jobs never block a request: the server queues them (`jobs.py`, one
  picture at a time) and the page asks for progress.
- **Nothing hard-coded.** Folders, device, safety and the 3060 switch live in
  `server/settings.json` (shared) and `server/settings.local.json` (this
  machine only, git-ignored, written by the Settings page). Model, LoRAs,
  prompt wording, size and steps live in the theme files.
- **Safe for work, always.** Every picture goes through `server/safety.py`
  (two nudity checkers, either one can block) before anyone sees it, and
  the safety negative words are added to every prompt. There is no switch
  to turn this off. Don't add NSFW LoRAs or themes.

## Models and files (git-ignored)

```
server/aIModels/   checkpoints, plus:
  sdxl-config/       SDXL config + tokenizer files (no weights), so SDXL
                     single-file models load offline
  sdxl-vae-fp16-fix/ VAE used by the "3060 settings"
  safety/            the two nudity checkers (Falconsai, AdamCodd)
server/lora/       LoRAs
server/theme/      theme JSON files (these ARE committed)
outputs/           pictures: new/ (unsaved) and characters/<name>/
```

These came from the old project (`/home/game-pc/image-generator`, read
only: never edit it). Current theme: `cel-shade.json` = WAI Illustrious
v17 (SDXL) + `chibi-style-xl` LoRA at 0.7. That checkpoint *can* draw adult
content like any anime SDXL model, so the safety check is what keeps it SFW.
On the 3060: about 25 s a picture (832×1216, 28 steps), ~5 s to load.

## Moving to the Mac (notes for phase 6)

- **Copy the folders above** (`server/aIModels/`, `server/lora/`) to the
  Mac; they are not in git. `start.py` installs the same packages; PyPI's
  torch on macOS uses the GPU through MPS (no CUDA packages).
- **Turn "Use 3060 settings" off** on the Settings page. The Mac has the
  memory, so the stock VAE in full precision and no tiling are fine. (If
  the stock SDXL VAE gives black or noisy pictures on MPS in half
  precision, either keep the fp16-fix VAE without tiling, or run the VAE in
  float32: test, don't guess.)
- `settings.local.json` is per machine: the Mac starts with the defaults
  from `settings.json` (3060 settings off, device auto → mps).
- **Time it on the Mac** (same prompt, seed and steps) and write the number
  here. Then try the MLX / Core ML versions of the same model in phase 7 as
  new backends in `server/backends/` (same `Backend(device).make(req,
  on_step)` shape), named by the theme's `"backend"` key.
- PyTorch's `expandable_segments` setting in `server/__main__.py` is for
  NVIDIA only and is ignored on the Mac.
- The safety checkers run on the CPU everywhere; that's fine on the Mac.

## Layout

```
start.py              sets up .venv, then runs the server
server/app.py         routes
server/settings.py    reads settings.json (+ settings.local.json)
server/themes.py      reads the theme folder
server/jobs.py        the picture queue (progress for the page)
server/generation.py  theme + prompt -> checked picture
server/backends/      one file per way of running a model (diffusers_sdxl.py)
server/safety.py      the nudity check
server/pictures.py    outputs/ on disk, saving to characters, the library list
web/                  index.html, app.css, js/ (main, theme-picker, create,
                      library, settings)
```

## Plan

Each phase is a small story. Finish, check at phone and desktop width,
commit, then move on.

- [x] **Phase 0 — Shell.** Page with theme picker, prompt, Generate button,
  empty result. Generate says "Not connected yet".
- [x] **Phase 1 — Themes as files.** Each theme is a JSON file in `server/theme/`
  (name, hint, later: model, LoRAs, prompt wording, size). Server reads the
  folder; adding a theme needs no code change. (Not done yet: remember the
  last theme and prompt on the phone.)
- [x] **Phase 2 — Jobs with a fake generator.** Generate creates a job; the
  server makes a placeholder picture with Pillow (prompt text on a coloured
  card) after a short delay. Page shows "waiting / working / done", then the
  picture. Pictures saved to `outputs/` with their settings beside them.
  This builds the whole flow before any AI is involved.
- [x] **Phase 3 — First real model.** One model via `diffusers` (likely an
  SDXL / Illustrious checkpoint for character art: small enough to also
  test on the 3060). Device picked automatically (CUDA here, MPS on the
  Mac). Model path in settings, not in code. Model stays loaded between
  pictures. Real progress steps.
- [x] **Phase 4 — Themes drive the model.** A theme picks its backend,
  model, LoRAs, extra prompt words, negative prompt and picture size.
- [ ] **Phase 5 — Library.** Started: pictures are saved per character
  (name field + Save) and the Library lists characters with their first
  picture. Still to do: open a character, see each picture's prompt and
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
