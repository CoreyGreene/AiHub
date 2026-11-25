# Image AI

A website for making pictures: pick a theme, type a prompt, press Generate.
It's one of the tools in AiHub (`apps/image`).

Pick a theme, type a prompt, press Generate. The picture is made on this
computer's graphics card and checked for nudity before it's shown (the
site is safe for work). Give it a character name and Save to keep it in
the Library.

**Models aren't in git.** Under AiHub, models come from the hub's models
folder (`ImageModels`) and the nudity checkers from its shared
`SafetyModels`. On its own, models go in `server/aIModels/`. LoRAs go in
`server/lora/` either way. Themes are JSON files in `server/theme/` (also
not in git: they're your own settings): add a file to add a theme, no code
change. **How to set up a theme, and where models and LoRAs go:** [server/theme/README.md](server/theme/README.md).

## Start it

Open its tile in AiHub (`python3 start.py` at the repo root, then
http://localhost:8000). It shows at `/image/`. The hub doesn't make the
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

Ground rules:

- Phone first. Every screen should work well at phone width.
- Image and pixel work happens on the server in Python, never in browser
  JavaScript.
- No browser pop-ups (`confirm()`, `alert()`): show questions and messages
  inside the page.

## API

| Call | What it does |
| --- | --- |
| `GET /api/themes` | List of themes |
| `GET /api/themes/details` | Every theme in full, for the Theme tab |
| `GET /api/themes/choices` | Model and LoRA files here, and the samplers |
| `PUT /api/themes/{id}` | Save changes to a theme (Theme tab → Edit → Change) |
| `POST /api/themes` | Make a new theme file (Theme tab → New) |
| `GET /api/files/{kind}/{name}/check?size=` | Before adding a model or LoRA: is the name fine, is it new, is there room? `kind` is `model` or `lora` |
| `PUT /api/files/{kind}/{name}` | Add a model or LoRA: the `.safetensors` file is the request body. Checked, then put in the models or LoRA folder |
| `POST /api/unlock` | The lock page sends the six-digit code (`{"code"}`); `{"open": true}` sets a 30-day cookie. While the code lock is on, every other route answers 401 `locked` without that cookie |
| `GET /api/custom` | Where the Custom tab starts (`custom` in settings.json) |
| `POST /api/generate` `{theme, prompt, count, words, custom}` | Queues `count` pictures (default 1, up to `max_pictures` in settings), answers `{"job"}`. `words` (Advanced tab): `{prompt_before, prompt_after, negative}` used in place of the theme's own, for these pictures only. `custom` (Custom tab, no theme): `{model, loras, prompt_before, prompt_after, negative, width, height, steps, guidance, scheduler}` |
| `GET /api/jobs/{job}` | Progress: `status` waiting / working (with `number` of `count`, `stage`, `step`, `steps`) / done (with `pictures`, and `blocked` = how many failed the safety check) / blocked / failed |
| `GET /api/workflows` | Saved workflows: `id`, `name`, how many `items` (newest first) |
| `POST /api/workflows` `{name}` | A new, empty workflow; answers `{"id"}` |
| `GET /api/workflows/{id}` | One workflow: `name` and its `items` (each is what Generate takes, plus a `name` for staging), `running`, and `run`: how its last Start is going, one per item (job status, `staging` group and `folder`) |
| `POST /api/workflows/{id}/start` | Queues every item; pictures go to staging under the item's name (or the workflow's name + its number). A running workflow can't be changed or deleted |
| `PUT /api/workflows/{id}` `{name, items}` | Saves the whole workflow; each item is checked like Generate |
| `DELETE /api/workflows/{id}` | Deletes the workflow (pictures already made stay) |
| `GET /api/experiments` | Saved experiments (`id`, `name`, how many `batches`), the `models` a batch can use (with `here` and their defaults), and every run |
| `POST /api/experiments` `{name, seed, batches}` | A new experiment; answers `{"id"}`. Each batch: `name`, `model`, `prompts`, `count`, and `width`, `height`, `steps`, `guidance` (0 = the model's own), `negative` |
| `GET` / `PUT` / `DELETE /api/experiments/{id}` | One experiment: read, save, delete (its runs stay) |
| `POST /api/experiments/{id}/start` | Queues every batch in order, same seeds for all; answers `{"run"}` (its folder in `outputs/experiments/`) |
| `GET /api/experiment-runs/{run}` | A run: each batch's status, pictures (with prompt number and seed), seconds a picture, folder |
| `POST /api/experiment-runs/{run}/stop` | Takes the run's waiting pictures out of the queue |
| `DELETE /api/experiment-runs/{run}` | Deletes the run's folder and its pictures (not while running) |
| `GET /api/staging` | Library → Staging: the groups of workflow pictures waiting to be picked |
| `GET /api/staging/{folder}` | One staging group and its pictures |
| `POST /api/staging/approve` `{ids, character}` | Moves the chosen staging pictures to a character (new or existing) |
| `GET /api/queue` | Picture jobs being made or waiting, in order |
| `DELETE /api/queue/{job}` | Remove a job (a waiting one is dropped; the one being made stops after its current step). The queue holds at most `max_queue` (500) jobs |
| `GET /api/characters` | Saved characters, each with its first picture |
| `GET /api/characters/{folder}` | One character and all its pictures (prompt, theme, date) |
| `GET /api/status` | `gpu`: graphics card name, memory used on the whole card / taken by this site / total (GB). `queue`: picture jobs `working` and `waiting` |
| `GET`/`POST /api/settings` | The "Use 3060 settings" switch (this machine only) |
| `GET /api/pictures/{id}` | A picture (`?download=1` to save it as a file) |
| `GET /api/pictures-zip?ids=a,b&name=…` | Several pictures in one zip, named after the character if given (computer only; phones download one by one) |
| `GET /api/pictures/{id}/recipe` | Library → Copy settings: the prompt, character, `theme` (its id if that theme is still there, else "") and `words` (the theme's words it was made with, or null) for the Advanced tab, and every setting (model, LoRAs, words, size, steps, guidance, sampler) as `custom`, for the Custom tab when there's no theme. `complete` is false for older pictures, whose missing settings come from their theme as it is now |
| `POST /api/pictures-delete` | Delete saved or staged pictures for good (`{"ids": [...]}`); a character or staging group with none left goes too |
| `POST /api/pictures/{id}/edit` `{prompt}` | Edit: change the picture by an instruction ("make the cloak red"); returns `{job}` like Generate, and the job's picture is a new one (the old one stays) |
| `POST /api/pictures/{id}/save` `{character}` | Saves the picture to that character |
