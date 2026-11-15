# AGENTS.md

A short guide for AI coding helpers (and people) working on ImageAi.

## What it is

A small website for making game art: pick a theme, type a prompt, get a
picture. It's built for one person, used mostly from a phone. The server
runs the image model on the same machine (an NVIDIA card, Apple Silicon or
the CPU).

## Run it

```bash
python3 start.py            # makes .venv, installs requirements, starts on port 8100
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
- **Pictures:** `server/generation.py` is the only way in. Behind it, each
  way of running a model is a small backend in `server/backends/` with the
  same shape (`Backend(device).make(req, on_step)`); a theme names its
  backend. The Edit button (change a picture by an instruction) uses the
  `qwen-edit` backend, set in the `"edit"` block of `settings.json`.
- **Memory:** measured, not set (`settings.memory_gb()`). Below the edit's
  `roomy_gb` it's squeezed in (4-bit text reader, parts taking turns); a
  big machine loads it whole.
- **Queue:** `server/jobs.py` makes one picture job at a time; the page
  asks for progress. The model stays loaded, and is let go when idle.
- **Settings:** `server/settings.json` (shared) and
  `server/settings.local.json` (this machine, git-ignored).
- **Themes:** one JSON file each in `server/theme/` (git-ignored, personal).
  Generic examples are in `server/theme/examples/`. The Theme tab can
  change them (Edit) and make new ones (New).
- **Workflows:** `server/workflows.py`, one JSON file each in
  `server/workflow/` (git-ignored, personal). A workflow is a list of
  items; each is what the Advanced / Custom tab sends to Generate, plus a
  name. Items are added and changed on the Create tab itself ("add mode",
  `web/js/create.js`), so the form is always the same one. Start queues
  every item; the pictures go to `outputs/staging/<group>/` (Library →
  Staging), where you choose which to move to a character.
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
- **Image work on the server**, in Python. The browser only shows pictures
  and sends requests.
- **No browser pop-ups** (`alert`, `confirm`, `prompt`). Ask and tell inside
  the page.
- **Cross-platform.** `pathlib`, no shell scripts needed, no hard-coded
  paths. Pick the device in code: `cuda`, then `mps`, then `cpu`.
- **Plain, simple words** in the page and its messages.
- **Safe for work, always.** Every picture goes through `server/safety.py`;
  there is no switch to turn it off. No NSFW themes or LoRAs.
- **Keep it lean.** Add only what's needed; remove experiments that didn't
  work out.

## This repo is public

- Never commit models (checkpoints, LoRAs, VAEs…), pictures, theme files,
  `*.local.json` or `.env`. `.gitignore` covers them; check `git status`
  before every commit.
- Nothing private in files or commit messages: no keys, passwords, personal
  paths, machine names, addresses or emails.
- Don't write a personal theme's model, LoRA or prompt words into committed
  files or commit messages.
