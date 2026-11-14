# ImageAi

A website for making pictures: pick a theme, type a prompt, press Generate.

**No AI yet.** Pressing Generate waits about 5 seconds, then shows a
built-in demo picture (a stick figure) that you can download. No models,
no downloads needed.

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
  themes.py           the list of themes (placeholders for now)
  generation.py       where image making plugs in (fake for now)
  assets/demo.png     the demo picture
web/                  the page your browser loads
  index.html
  app.css             mobile first; wider screens get a two-column layout
  app.js              shows things and talks to the server, nothing more
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
| `POST /api/generate` `{theme, prompt}` | Waits ~5 s, then answers `{"status": "done", "image": "api/demo-image", ...}` |
| `GET /api/demo-image` | The demo picture (`?download=1` to save it as a file) |
