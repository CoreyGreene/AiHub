# AGENTS.md

A short guide for AI coding helpers (and people) working on MovieAi.

## What it is

A small website for making short videos for games: pick a theme, type a
prompt, get a video. It's built for one person, used mostly from a phone.
The server runs the video model on the same machine (an NVIDIA card, Apple
Silicon or the CPU). A sister project of ImageAi, built the same way.

**Not connected yet:** no video backend is written, so Generate answers "Not
connected yet" (job status `not_ready`). Everything around it works.

## Run it

```bash
python3 start.py            # makes .venv, installs requirements, starts on port 8200
python3 start.py --port 9000
```

It listens on `0.0.0.0` so a phone on the same network can reach it.
Models aren't included: see [server/theme/README.md](server/theme/README.md)
for where they go and how to write a theme.

## How it's built

- **Server:** FastAPI + uvicorn in `server/`. The page is static files; all
  else is JSON under `/api/` (listed in [README.md](README.md)).
- **Page:** plain HTML, CSS and ES modules in `web/`. No framework, no npm,
  no build step: edit a file, reload.
- **Videos:** `server/generation.py` is the only way in. Behind it, each
  way of running a model is a small backend in `server/backends/` with the
  same shape (`Backend(device).make(req, on_step)` → a list of frames); a
  theme names its backend. `server/videos.py` writes the `.mp4` and its
  first frame (`.jpg`).
- **Queue:** `server/jobs.py` makes one video job at a time; the page
  asks for progress. The model stays loaded, and is let go when idle.
- **Settings:** `server/settings.json` (shared) and
  `server/settings.local.json` (this machine, git-ignored).
- **Themes:** one JSON file each in `server/theme/` (git-ignored, personal).
  Generic examples are in `server/theme/examples/`. The Theme tab can
  change them (Edit) and make new ones (New).
- **Code lock:** `server/lock.py` + `web/lock.html`. A server option, off by
  default and not on the website: `"lock": true` and `"lock_code"` in
  `server/settings.local.json`, then restart. With it on, every route needs
  a cookie got by typing the six-digit code.
- **Adding models and LoRAs from the page:** `server/uploads.py` streams the
  file to disk (never all in memory), checks it, then names it. Only
  `.safetensors`.

## Rules

- **Phone first.** Every screen works at 375px wide; big tap targets, 16px
  inputs. Check desktop width too.
- **Video work on the server**, in Python. The browser only plays videos
  and sends requests.
- **No browser pop-ups** (`alert`, `confirm`, `prompt`). Ask and tell inside
  the page.
- **Cross-platform.** `pathlib`, no shell scripts needed, no hard-coded
  paths. Pick the device in code: `cuda`, then `mps`, then `cpu`.
- **Plain, simple words** in the page and its messages.
- **Safe for work, always.** Every video goes through `server/safety.py`
  (frames from all through it);
  there is no switch to turn it off. No NSFW themes or LoRAs.
- **Keep it lean.** Add only what's needed; remove experiments that didn't
  work out.

## This repo is public

- Never commit models (checkpoints, LoRAs, VAEs…), videos, pictures, theme files,
  `*.local.json` or `.env`. `.gitignore` covers them; check `git status`
  before every commit.
- Nothing private in files or commit messages: no keys, passwords, personal
  paths, machine names, addresses or emails.
- Don't write a personal theme's model, LoRA or prompt words into committed
  files or commit messages.
