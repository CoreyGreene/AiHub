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
- **Ask → Advanced:** the same, with more Thinking levels: Long (no limit), Medium (up to 4,000 thinking tokens),
  Short (up to 1,000) and Off. Gemma 4 and Qwen3.5 only have thinking on or off, so the budgets are CodeAi's own:
  when the thinking reaches the budget, CodeAi stops it and has the model answer from its notes (the answer says so).
- **Thinking** (under Model): a model's thinking choices, from `thinking_levels` in `settings.json` (`where` says
  which sub-tab shows each). Standard has On and Off; a model with none hides it.
- **It can look at your files**, read only, in the `folders` listed in `settings.local.json` (Desktop, Documents,
  Downloads): list a folder, find files by name, read a file, search. "Looked at N things" in the answer shows
  what it read.
- **Can change files** (a switch, off every time the page opens): for that question it may also make and change
  text files in the same folders (never delete, never inside `.git` or `.venv`). It can mark a file runnable
  itself (`write_file` with `runnable: true`, or `make_runnable`), and scripts (a `#!` first line, or `.command`,
  `.sh`, `.zsh`) are marked runnable anyway. For something to double-click, it writes a `.command` launcher (a
  `.py` opens in an editor on a Mac). "Made runnable" shows in the answer's changes, and Undo takes it back. Each file is copied to `backups/`
  first; the answer shows "Changed N files" with each change, and **Undo these changes** puts them all back (a
  file changed again since is left alone).
- **Bulk:** one prompt over a long list of items, such as "change these 300 lines of dialogue". Everything about
  the job is in a **bulk file** you give it (JSON): the prompt, the items, and optionally the checks and a review.
  CodeAi has no knowledge of any one kind of job, so a new kind of bulk job is a new file, never a code change.
  Choose or paste the file, pick the folder it works in (it looks only there), check the model and Thinking (the
  file fills them in), and press **Start**. Each item is asked **on its own, with a fresh memory**: the model sees the prompt filled
  in with that one item, never the items before it, so the 500th is as quick and careful as the first and a slip in
  one can't spill into the next. Items go into the queue one at a time, so a question you ask meanwhile waits for one
  item at most.
  - **The file:** `prompt` (one string, or a list of lines) with `{field}` for each item's parts and `{folder}`;
    `items` (a list of objects, each with all its fields). Optional: `name` (else the file's name), `model`,
    `thinking`, `can_change_files` (on unless it says `false`), `search`, `checks`, `review`, `retries` (1),
    `max_steps`. The page warns when items are missing a `{field}` the prompt uses. [examples/README.md](examples/README.md) explains each, with example files.
  - **search:** text CodeAi looks for in the folder before the model starts (e.g. `"{old}"`), so it starts at the
    right lines.
  - **checks:** CodeAi's own tests of what an item changed: `changed`, `lines` (how many, changed in place), `had`
    and `has` (a changed line held / now has some text, exactly or most of its words), `kept` (what a regex matches
    stays the same, e.g. a speaker's name or #tags), `lacks` (no changed line matches a regex). **review:** a second prompt, asked fresh with the change in
    front of it, that answers PASS or FAIL. A failed check or review undoes the item and tries it once more with the
    reason; still wrong, it's undone and marked "failed check".
  - The dialogue examples: `dialogue-replace.json` swaps lines for exact new words (thinking off, about 20 s a line);
    `dialogue-rework.json` takes a rough idea and has Gemma make the line read right in the character's voice
    (thinking Short: with no limit Gemma sometimes thought for 15-25 minutes over one line), with a review.
  - A run's page shows each item (its fields, the check, the review, the model's note, the tools it used, the diff)
    with filters by status, **Undo this item**, **Stop**, **Carry on**, **Try the failed ones again**, **Undo the
    whole run** and **Download results**. Runs are kept in `bulk/` (one JSON each), saved after every item; one
    going when CodeAi stopped shows as paused, and Carry on picks it up.
- **History:** every conversation (one JSON file each in `history/`), newest first. Open one to carry it on. **Delete all** (it asks first) clears them, except one still being answered.
- **Settings (gear):** which model is loaded, a button to let it go, and the queue with a Stop for each question.
- **The top line:** the model loaded, the GPU memory in use (whole Mac) and the model's share, and the queue.

## How it's laid out

```
start.py              one way to start it (sets up .venv, then runs the server)
server/
  app.py              web routes: serves web/ and the /api calls
  jobs.py             the question queue: one answered at a time
  bulk.py             bulk runs: a file's prompt over its items, a fresh memory each, checked
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
| `DELETE /api/history` | Delete every conversation (one still being answered is kept): `{deleted, kept}` |
| `POST /api/history/{id}/undo/{index}` | Put back the files answer number `index` changed |
| `GET /api/bulk` | Every bulk run, newest first, with counts by status |
| `POST /api/bulk` `{file, folder, model, thinking, can_change_files, name, source}` | Start a run from a bulk file (`{prompt, items, ...}`); the other fields, when given, win over the file's |
| `GET /api/bulk/{run}` | One run with every item: `status` waiting / working / reviewing / done / failed / unchanged / error / stopped / undone, `check`, `review`, `answer`, `steps`, `changes` |
| `POST /api/bulk/{run}/stop`, `/carry-on` (`?redo=true` retries failed ones), `/undo`, `/undo/{n}` | Stop it, start it again, undo all of it or one item |
| `DELETE /api/bulk/{run}` | Delete a run's record (its files stay as they are) |
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
| `codeai_bulk_start` | Start a bulk run from a bulk `file` (the JSON, or a path to it); `folder`, `model`, `thinking` win over the file's |
| `codeai_bulk_status` | A run's progress and its problem items, waiting up to `wait_seconds`; with no run, the recent runs |
| `codeai_bulk_stop` | Stop a run |

Added to Claude Code for every project in `~/.claude.json` (`mcpServers.codeai`: this folder's `.venv/bin/python`
running `connector/codeai_mcp.py`). New sessions pick it up.
