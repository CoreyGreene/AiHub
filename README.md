# CodeAi

A website for asking local AI models about code: pick a model, ask, and watch the answer being written. Code comes
in code windows with a Copy button. The same look and layout as ImageAi; one of a family of local AI tools.

The models run on this Mac (MLX, Apple's GPU), one at a time, and are let go after a while with no questions.

## Start it

```bash
python3 start.py
```

The first run makes a private Python environment in `.venv` and installs what it needs (with `uv` if it's
installed, which reuses packages other projects already downloaded). If `python3` is too old (a Mac's own is 3.9),
it finds a newer one by itself.

It prints two addresses: **on this computer** `http://localhost:8200`, and **from your phone** (same Wi-Fi).
Stop it with Ctrl+C. Another port: `python3 start.py --port 9000`.

**Models** are listed in `server/settings.local.json` (this machine's folders, not in git): an id, a name, the
model's folder, a note, and any extra settings for mlx_lm's server. The first is the default.

## The page

- **Ask → Standard:** the model, your question, Ask (or ⌘ Enter). Asking again carries the conversation on; **New
  conversation** starts fresh. The answer shows its thinking (folded away), then the answer, then the model, time
  and speed. **Stop** stops it; what it wrote so far is kept.
- **Thinking** (under Model): a model's thinking choices, from `thinking_levels` in `settings.json`. Gemma 4 and
  Qwen3.5 have On and Off; a model with none hides it.
- **It can look at your files**, read only, in the `folders` listed in `settings.local.json` (Desktop, Documents,
  Downloads): list a folder, find files by name, read a file, search. "Looked at N things" in the answer shows
  what it read.
- **Can change files** (a switch, off every time the page opens): for that question it may also make and change
  text files in the same folders (never delete, never inside `.git` or `.venv`). Each file is copied to `backups/`
  first; the answer shows "Changed N files" with each change, and **Undo these changes** puts them all back (a
  file changed again since is left alone).
- **History:** every conversation (one JSON file each in `history/`), newest first. Open one to carry it on.
- **Settings (gear):** which model is loaded, a button to let it go, and the queue with a Stop for each question.
- **The top line:** the model loaded, the GPU memory in use (whole Mac) and the model's share, and the queue.

## How it's laid out

```
start.py              one way to start it (sets up .venv, then runs the server)
server/
  app.py              web routes: serves web/ and the /api calls
  jobs.py             the question queue: one answered at a time
  models.py           loads a model (its own program), asks it, lets it go
  model_server.py     mlx_lm's server with MLX's memory cache capped
  history.py          conversations, one JSON file each
  memory.py           the memory line at the top
  settings.json       how it runs (settings.local.json: this machine, models)
web/                  the page: plain HTML, CSS and ES modules, no build step
```

## API

The page uses it, and so will Claude (an MCP connector, next).

| Call | What it does |
| --- | --- |
| `GET /api/status` | `memory` (total, used, the model's share, GB), `model` (loaded, loading), `queue` (answering, waiting) |
| `GET /api/models` | The models on this computer, and the default |
| `POST /api/ask` `{prompt, model, thinking, can_edit, conversation, source}` | Ask: a new conversation when `conversation` is empty. Answers `{job, conversation}` at once. `source`: `you` or `claude` |
| `GET /api/jobs/{job}` | Progress: `status` waiting (with `ahead`) / loading / thinking / answering / done / stopped / failed, the `thinking` and `answer` so far, `tokens`, `seconds`, `per_second` |
| `GET /api/queue` | Questions waiting or being answered, in order |
| `DELETE /api/queue/{job}` | Stop one (a waiting one is dropped; the one being answered stops where it is) |
| `GET /api/history` | Every conversation, newest first (no messages) |
| `GET /api/history/{id}` | One conversation with its messages, and `job` if it's still being answered |
| `DELETE /api/history/{id}` | Delete a conversation |
| `POST /api/history/{id}/undo/{index}` | Put back the files answer number `index` changed |
| `POST /api/model/unload` | Let go of the model now |

## Claude's connector (MCP)

`connector/codeai_mcp.py` lets Claude (or Codex, or any MCP client) use CodeAi: it calls the API above, so CodeAi
has to be running. No packages: MCP over stdio is one JSON message per line. Claude's questions go in the same
queue as yours and show "Claude asked" on the page.

| Tool | What it does |
| --- | --- |
| `codeai_ask` | Ask (a new conversation, or a follow-up with `conversation`; `can_change_files` to let it edit); returns a job id, or waits up to `wait_seconds` |
| `codeai_result` | A job's answer, waiting up to `wait_seconds` (default 120) for it |
| `codeai_queue`, `codeai_stop` | The queue; stop a job |
| `codeai_models` | The models, their thinking choices, and the folders they can read |
| `codeai_history` | Past conversations, or one in full |

Added to Claude Code for every project in `~/.claude.json` (`mcpServers.codeai`: this folder's `.venv/bin/python`
running `connector/codeai_mcp.py`). New sessions pick it up.
