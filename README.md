# AiHub

One website for local AI tools: a page of tiles (Image AI, 3D AI, Code AI, Movie AI). Open a tile and that tool
starts and shows its own pages. A bar at the top of every page shows what's running and how much memory it uses,
with a Stop button. Every prompt box gets a 🎤 button: say it, and the words are typed in (Whisper, on this
Mac). Browsers allow the mic only on a secure page, so for now that's on the Mac itself (`localhost`).

```bash
python3 start.py              # http://localhost:8000
python3 start.py --port 9000  # another port
```

Each tool lives in `apps/` with its own README. Set the folder that holds your AI models in
`hub/settings.local.json`:

```json
{"models_dir": "~/AIModels"}
```

Inside it, one folder per kind: `ImageModels`, `MeshModels`, `GeneralModels` (language models), `MovieModels`, and
`SafetyModels`: the nudity checkers every picture and video goes through, shared by Image AI and Movie AI, and
`SoundModels`: Whisper, for the 🎤 buttons.

## API

- `GET /hub/api/status`: each tool's state (running, starting, stopped, failed, not_set_up) and memory, and the
  computer's memory.
- `POST /hub/api/apps/{id}/start`, `POST /hub/api/apps/{id}/stop`
- `POST /hub/api/listen`: a recording in (the body), its words out (`{"text"}`); starts Speech if needed.
- `/{id}/…`: that tool's own pages and API.
