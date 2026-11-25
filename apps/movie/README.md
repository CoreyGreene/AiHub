# Movie AI

A website for making short videos: pick a theme, type a prompt, press
Generate. It's one of the tools in AiHub (`apps/movie`). The video is made
on this computer's graphics card and checked for nudity before it's shown
(the site is safe for work). Give it a character name and Save to keep it
in the Library.

**Video models:** Wan through diffusers (a small one, Wan 2.1 1.3B, works on
a 12 GB card), and on a Mac LTX-2.5 through MLX, which makes the sound too.
An LTX theme can begin from a **start picture** (Create → Start picture;
Rotate turns it a quarter turn), and the video takes the picture's shape.
Where to get the models and how to make a theme:
[server/theme/README.md](server/theme/README.md). Without a model or the
video packages, Generate answers "Not connected yet".

**Models aren't in git.** Under AiHub, models come from the hub's models
folder (`MovieModels`) and the nudity checkers from its shared
`SafetyModels`. On its own, models go in `server/aIModels/`. LoRAs go in
`server/lora/` either way. Themes are JSON files in `server/theme/` (also
not in git: they're your own settings): add a file to add a theme, no code
change.
**How to set up a theme, and where models and LoRAs go:**
[server/theme/README.md](server/theme/README.md).

## Start it

Open its tile in AiHub (`python3 start.py` at the repo root, then
http://localhost:8000). It shows at `/movie/`. The hub doesn't make the
tool's `.venv`: run it on its own once first, or the tile says "Not set up
yet".

On its own: you need Python 3.10 or newer. Same command on Linux and macOS,
in this folder:

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
requirements.txt      Python packages
server/               the Python side
  __main__.py         starts the web server, prints the addresses
  app.py              web routes: serves web/ and the /api calls
  settings.json       folders, device, safety (settings.local.json: this machine)
  themes.py           reads the theme files in theme/
  jobs.py             the video queue
  generation.py       theme + prompt -> a checked video
  backends/           ways of running a video model (diffusers_wan.py: Wan; ltx_mlx.py: LTX-2.5)
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
| `GET /api/themes` | List of themes (`start_picture`: can it begin from one) |
| `GET /api/themes/details` | Every theme in full, for the Theme tab |
| `GET /api/themes/choices` | Model folders/files and LoRA files here, and the samplers |
| `PUT /api/themes/{id}` | Save changes to a theme (Theme tab → Edit → Change) |
| `POST /api/themes` | Make a new theme file (Theme tab → New) |
| `GET /api/files/{kind}/{name}/check?size=` | Before adding a model or LoRA: is the name fine, is it new, is there room? `kind` is `model` or `lora` |
| `PUT /api/files/{kind}/{name}` | Add a model or LoRA: the `.safetensors` file is the request body. Checked, then put in the models or LoRA folder |
| `POST /api/unlock` | The lock page sends the six-digit code (`{"code"}`); `{"open": true}` sets a 30-day cookie. While the code lock is on, every other route answers 401 `locked` without that cookie |
| `GET /api/custom` | Where the Custom tab starts (`custom` in settings.json) |
| `POST /api/start-pictures` | Create → Start picture: the picture is the request body (40 MB at most). Answers `{id, image}` |
| `POST /api/start-pictures/{id}/rotate` | A quarter turn clockwise, kept as a new picture. Answers `{id, image}` |
| `GET /api/start-pictures/{id}` | A start picture |
| `POST /api/generate` `{theme, prompt, count, words, custom, start_picture}` | Queues `count` videos (default 1, up to `max_videos` in settings), answers `{"job"}`. `words` (Advanced tab): `{prompt_before, prompt_after, negative}` used in place of the theme's own, for these videos only. `custom` (Custom tab, no theme): `{model, loras, prompt_before, prompt_after, negative, width, height, frames, fps, steps, guidance, scheduler}`. `start_picture`: an id from `/api/start-pictures`, only for themes that can begin from one (LTX; on the Custom tab, when its backend is LTX) |
| `GET /api/jobs/{job}` | Progress: `status` waiting / working (with `number` of `count`, `stage`, `step`, `steps`) / done (with `videos`: `{video, file, poster}` each, and `blocked` = how many failed the safety check) / blocked / not_ready (video packages not installed) / failed |
| `GET /api/queue` | Video jobs being made or waiting, in order |
| `DELETE /api/queue/{job}` | Remove a job (a waiting one is dropped; the one being made stops after its current step). The queue holds at most `max_queue` jobs |
| `GET /api/characters` | Saved characters, each with its first video's first frame |
| `GET /api/characters/{folder}` | One character and all its videos (prompt, theme, length, date) |
| `GET /api/status` | `gpu`: graphics card name, memory used on the whole card / taken by this site / total (GB). `queue`: video jobs `working` and `waiting` |
| `GET`/`POST /api/settings` | The "Use 3060 settings" switch (this machine only) |
| `GET /api/videos/{id}` | A video, `.mp4` (`?download=1` to save it as a file) |
| `GET /api/videos/{id}/poster` | The video's first frame (`.jpg`) |
| `GET /api/videos-zip?ids=a,b&name=…` | Several videos in one zip, named after the character if given (computer only; phones download one by one) |
| `GET /api/videos/{id}/recipe` | Library → Copy settings: the prompt, character and every setting (model, LoRAs, words, size, frames, fps, steps, guidance, sampler) to make it again on the Custom tab. `complete` is false for older videos, whose missing settings come from their theme as it is now |
| `POST /api/videos-delete` | Delete saved videos for good (`{"ids": [...]}`); a character with none left goes too. Only videos saved in the Library |
| `POST /api/videos/{id}/save` `{character}` | Saves the video to that character |
