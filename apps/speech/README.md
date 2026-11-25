# Speech

A small helper for AiHub's 🎤 buttons: a recording in, the words said in it out. Whisper through MLX, so it
runs on a Mac. It has no tile: the hub starts it the first time a mic button is used, and it lets go of the
model after a few idle minutes.

- Model: a Whisper folder in MLX format (for example `mlx-community/whisper-large-v3-turbo`) in the hub's
  `SoundModels` folder; `model` in `server/settings.json` names it.
- `POST /api/transcribe` with the recording as the body (webm, mp4, m4a, wav) gives `{"text": "..."}`.
  The hub's `/hub/api/listen` sends it here.
- Needs ffmpeg (`brew install ffmpeg`). Nothing is downloaded while it runs.
