# ImageAi

A website for making pictures: pick a theme, type a prompt, press Generate.

Pick a theme, type a prompt, press Generate. The picture is made on this
computer's graphics card and checked for nudity before it's shown (the
site is safe for work). Give it a character name and Save to keep it in
the Library.

**Models aren't in git.** Put them in `server/aIModels/` and LoRAs in
`server/lora/`. Themes are JSON files in `server/theme/` (also not in git:
they're your own settings): add a file to add a theme, no code change. **How to set up a theme, and where models and
LoRAs go:** [server/theme/README.md](server/theme/README.md).

## Start it

You need Python 3.10 or newer. Same command on Linux and macOS:

```bash
python3 start.py
```

The first run takes a minute: it makes a private Python environment in
`.venv` and installs what it needs. After that it starts straight away.

It prints two addresses:

- **On this computer:** `http://localhost:8100`
- **From your phone:** `http://<this computer's address>:8100` (same Wi-Fi,
  or Tailscale later)

Stop it with Ctrl+C.

### Another port

```bash
python3 start.py --port 9000
```

You can also set `IMAGEAI_PORT=9000`. To allow only this computer (not your
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
  jobs.py             the picture queue
  generation.py       theme + prompt -> a checked picture
  backends/           ways of running a model (diffusers SDXL for now)
  safety.py           the nudity check
  gpu.py              graphics card name and memory, for the top of the page
  pictures.py         keeps pictures in outputs/ (new ones, and saved per character)
  theme/              your theme files (JSON, not in git), the guide, examples/
  aIModels/, lora/    models and LoRAs (not in git)
web/                  the page your browser loads
  index.html
  app.css             mobile first; wider screens get a two-column layout
  js/                 main.js loads the rest: theme picker, create, library, settings
```

Ground rules carried over from the last project:

- Phone first. Every screen should work well at phone width.
- Image and pixel work happens on the server in Python, never in browser
  JavaScript.
- No browser pop-ups (`confirm()`, `alert()`): show questions and messages
  inside the page.

## API

| Call | What it does |
| --- | --- |
| `GET /api/themes` | List of themes |
| `POST /api/generate` `{theme, prompt, count}` | Queues `count` pictures (default 1, up to `max_pictures` in settings), answers `{"job"}` |
| `GET /api/jobs/{job}` | Progress: `status` waiting / working (with `number` of `count`, `stage`, `step`, `steps`) / done (with `pictures`, and `blocked` = how many failed the safety check) / blocked / failed |
| `GET /api/queue` | Picture jobs being made or waiting, in order |
| `DELETE /api/queue/{job}` | Remove a job (a waiting one is dropped; the one being made stops after its current step). The queue holds at most `max_queue` (500) jobs |
| `GET /api/characters` | Saved characters, each with its first picture |
| `GET /api/status` | `gpu`: graphics card name, memory used on the whole card / taken by this site / total (GB). `queue`: picture jobs `working` and `waiting` |
| `GET`/`POST /api/settings` | The "Use 3060 settings" switch (this machine only) |
| `GET /api/pictures/{id}` | A picture (`?download=1` to save it as a file) |
| `GET /api/pictures-zip?ids=a,b&name=…` | Several pictures in one zip, named after the character if given (computer only; phones download one by one) |
| `POST /api/pictures/{id}/save` `{character}` | Saves the picture to that character |
