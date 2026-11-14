# MovieAi

A website for making short videos: pick a theme, type a prompt, press
Generate. The video is made on this computer's graphics card and checked
for nudity before it's shown (the site is safe for work). Give it a
character name and Save to keep it in the Library.

**Not connected yet.** The whole website works (themes, Custom, Advanced,
Library, Settings, the queue, the code lock), but no video model is set up,
so Generate answers "Not connected yet". Video making comes with the Mac.

**Models aren't in git.** Put them in `server/aIModels/` and LoRAs in
`server/lora/`. Themes are JSON files in `server/theme/` (also not in git:
they're your own settings): add a file to add a theme, no code change.
**How to set up a theme, and where models and LoRAs go:**
[server/theme/README.md](server/theme/README.md).

## Start it

You need Python 3.10 or newer. Same command on Linux and macOS:

```bash
python3 start.py
```

The first run takes a minute: it makes a private Python environment in
`.venv` and installs what it needs. After that it starts straight away.

It prints two addresses:

- **On this computer:** `http://localhost:8200`
- **From your phone:** `http://<this computer's address>:8200` (same Wi-Fi,
  or Tailscale later)

Stop it with Ctrl+C.

### Another port

```bash
python3 start.py --port 9000
```

You can also set `MOVIEAI_PORT=9000`. To allow only this computer (not your
phone), use `--host 127.0.0.1`.

## How it's laid out

```
start.py              one way to start it (sets up .venv, then runs the server)
requirements.txt      Python packages (the video ones are commented out for now)
server/               the Python side
  __main__.py         starts the web server, prints the addresses
  app.py              web routes: serves web/ and the /api calls
  settings.json       folders, device, safety (settings.local.json: this machine)
  options.json        the Advanced tab's choices (camera, motion, light, loop)
  themes.py           reads the theme files in theme/
  jobs.py             the video queue
  generation.py       theme + prompt -> a checked video
  backends/           ways of running a video model (none written yet)
  safety.py           the nudity check, on frames through the video
  gpu.py              graphics card name and memory, for the top of the page
  videos.py           keeps videos in outputs/ (new ones, and saved per character)
  uploads.py          models and LoRAs added from the page
  lock.py             the six-digit code lock
  theme/              your theme files (JSON, not in git), the guide, examples/
  aIModels/, lora/    models and LoRAs (not in git)
web/                  the page your browser loads
  index.html, lock.html
  app.css             mobile first; wider screens get a two-column layout
  js/                 main.js loads the rest: theme picker, create, library, settings
```

Ground rules:

- Phone first. Every screen should work well at phone width.
- Video and pixel work happens on the server in Python, never in browser
  JavaScript.
- No browser pop-ups (`confirm()`, `alert()`): show questions and messages
  inside the page.

## API

| Call | What it does |
| --- | --- |
| `GET /api/themes` | List of themes |
| `GET /api/themes/details` | Every theme in full, for the Theme tab |
| `GET /api/themes/choices` | Model folders/files and LoRA files here, and the samplers |
| `PUT /api/themes/{id}` | Save changes to a theme (Theme tab → Edit → Change) |
| `POST /api/themes` | Make a new theme file (Theme tab → New) |
| `GET /api/files/{kind}/{name}/check?size=` | Before adding a model or LoRA: is the name fine, is it new, is there room? `kind` is `model` or `lora` |
| `PUT /api/files/{kind}/{name}` | Add a model or LoRA: the `.safetensors` file is the request body. Checked, then put in the models or LoRA folder |
| `GET /api/options` | The Advanced tab's extra choices (from `server/options.json`) |
| `POST /api/unlock` | The lock page sends the six-digit code (`{"code"}`); `{"open": true}` sets a 30-day cookie. While the code lock is on, every other route answers 401 `locked` without that cookie |
| `GET /api/custom` | Where the Custom tab starts (`custom` in settings.json) |
| `POST /api/generate` `{theme, prompt, count, options, custom}` | Queues `count` videos (default 1, up to `max_videos` in settings), answers `{"job"}`. `options`: the Advanced choices. `custom` (Custom tab, no theme): `{model, loras, prompt_before, prompt_after, negative, width, height, frames, fps, steps, guidance, scheduler}` |
| `GET /api/jobs/{job}` | Progress: `status` waiting / working (with `number` of `count`, `stage`, `step`, `steps`) / done (with `videos`: `{video, file, poster}` each, and `blocked` = how many failed the safety check) / blocked / not_ready (no video model set up yet) / failed |
| `GET /api/queue` | Video jobs being made or waiting, in order |
| `DELETE /api/queue/{job}` | Remove a job (a waiting one is dropped; the one being made stops after its current step). The queue holds at most `max_queue` jobs |
| `GET /api/characters` | Saved characters, each with its first video's first frame |
| `GET /api/characters/{folder}` | One character and all its videos (prompt, theme, length, date) |
| `GET /api/status` | `gpu`: graphics card name, memory used on the whole card / taken by this site / total (GB). `queue`: video jobs `working` and `waiting` |
| `GET`/`POST /api/settings` | The "Use 3060 settings" switch (this machine only) |
| `GET /api/videos/{id}` | A video, `.mp4` (`?download=1` to save it as a file) |
| `GET /api/videos/{id}/poster` | The video's first frame (`.jpg`) |
| `GET /api/videos-zip?ids=a,b&name=…` | Several videos in one zip, named after the character if given (computer only; phones download one by one) |
| `POST /api/videos/{id}/save` `{character}` | Saves the video to that character |
