# AGENTS.md

A short guide for AI coding helpers (and people) working on CodeAi.

## What it is

A small website for asking local AI models about code, built for one person, used from a Mac or a phone. It's one
of a family of local AI tools (ImageAi is the other so far) that share a look and a shape: a page with tabs, a queue
on the server, and an API that Claude or Codex can use through an MCP connector.

## Run it

```bash
python3 start.py            # makes .venv, installs requirements, starts on port 8200
```

## How it's built

- **Server:** FastAPI + uvicorn in `server/`. The page is static files; all else is JSON under `/api/` (listed in
  [README.md](README.md)).
- **Page:** plain HTML, CSS and ES modules in `web/`. No framework, no npm, no build step. `app.css` starts with
  ImageAi's own styles so the two look the same: change shared looks in both.
- **Models:** `server/models.py` runs mlx_lm's server as its own program (`model_server.py`) on `model_port`, one
  model at a time; stopping it gives all its memory back. Answers stream from its OpenAI-style API.
- **Queue:** `server/jobs.py`, one worker, one question at a time. The page asks for progress (the answer so far)
  every 400 ms. The model is let go after `unload_after_minutes` with nothing asked.
- **Bulk:** `server/bulk.py`. A run queues its items one at a time as jobs with their own fresh messages, the
  run's folder as the tools' only folder (`tools.scoped`), and an `on_done` hook in place of History. Everything
  about a job (prompt, search, checks, review) comes from the bulk file: keep the code free of any one kind of job
  (no field names, file formats or task names in it). `CHECKS` are generic tests a file can combine; a failed one,
  or a review that says FAIL, undoes the item and retries it with the reason. Runs live in `bulk/` (git-ignored).
- **History:** `server/history.py`, one JSON file per conversation in `history/` (git-ignored).
- **Settings:** `server/settings.json` (shared) and `server/settings.local.json` (this machine: the model list).

## Rules

- **Mac first.** It runs models with MLX, on Apple silicon.
- **Phone first** for the page: every screen works at 375px wide; big tap targets, 16px inputs. Check desktop too.
- **No browser pop-ups** (`alert`, `confirm`, `prompt`). Ask and tell inside the page.
- **Plain, simple words** in the page and its messages.
- **Answers are escaped** before they're shown (`web/js/markdown.js`): a model's text never becomes page HTML.
- **Memory:** keep `prompt_cache_size` small. In the model tests, mlx_lm's default (10 past conversations) grew
  Gemma 4 31B to over 100 GB.
- **Keep it lean.** Add only what's needed.

## Nothing private in git

Conversations, logs and `*.local.json` stay on this machine (`.gitignore`). No personal paths, keys or machine names
in committed files or commit messages.
