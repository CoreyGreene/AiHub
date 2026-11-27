# Lights AI

The HALO Home (Avi-on) lights, from the Mac over Bluetooth, without the HALO Home app. A tab in AiHub, and Talk's
Octavia can use it: "turn off the fireplace and stair lights", "dim Main 3 to 40", "make all the lights warm".

## The page

One card for **All lights**, one per light, one per group. Each has an on/off switch (groups: On / Off), a
brightness slider and a warm ↔ cool slider (2700–5000 K) with quick picks. A change goes out when you let go of a
slider. It shows what the lights say about themselves, so changes from the wall or the HALO app show up too.

## How it works

- HALO Home lights form a Bluetooth mesh: connect to any one light and every light in the same home hears you.
- Each home ("location") has its own secret key. `halo.py login` gets it from Avi-on's cloud **once**; after that,
  everything is local.
- The lights advertise as "Avi-on" with the short id `FEF1`. macOS hides Bluetooth MAC addresses, which is why the
  ready-made libraries don't work on a Mac; this finds lights by their adverts instead.
- To tell your mesh from a neighbour's (your son's lights), it asks "everyone report in" with your key; only
  your own lights can read it.
- The server stays connected, reconnects when the link drops, and asks the lights how they are every 5 minutes.
- "On" with no brightness puts a light back to how bright it was.
- Built on [recsrmesh](https://pypi.org/project/recsrmesh/) (CSRMesh encryption) and [bleak](https://pypi.org/project/bleak/)
  (Bluetooth). The Avi-on message format comes from [avionmesh](https://pypi.org/project/avionmesh/).

## Files

- `halo_mesh.py`: the mesh side (saved file, names, messages, the Bluetooth link). Shared.
- `halo.py`: the command line: `login`, and tests (`list`, `scan`, `status`, `on`, `off`, `dim`, `temp`).
- `server/`: the server (`home.py` keeps the connection and the lights' state; `app.py` the routes). Port 8710.
- `web/`: the page (plain HTML, CSS and JS).
- `lights.local.json`: the mesh keys and light list. Private (chmod 600), never in git.

## API

```
GET  /api/lights     every home: connected?, each light (on, brightness %, kelvin), the groups
POST /api/set        {"lights": ["fireplace", "stair"] | "all" | "main 3", "on": true, "brightness": 40, "kelvin": 2700}
POST /api/refresh    ask every light how it is now
```

## Set up and run

```bash
cd ~/Documents/repos/Ai-Hub/apps/lights
python3 start.py                       # makes .venv on the first run; normally AiHub starts it
.venv/bin/python halo.py login         # once per HALO Home account (adds, never replaces)
```

Bluetooth permission belongs to the app that started AiHub (Terminal, if you start it there).
