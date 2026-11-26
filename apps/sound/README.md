# Sound AI

Make sound effects with Stable Audio 3 Small SFX. Generate from a prompt, play the result, then give it a name and save it to the Library. Download any sound as a stereo 16-bit WAV. Recent and saved sounds live in `outputs/`.

AiHub starts Sound AI on port 8610 from its tile. Set it up once with `python3 apps/sound/start.py` and stop it with Ctrl+C when the server starts. The tool uses its own Python environment. AiHub points it at `SoundModels/stable-audio-3-small-sfx`, including the checkpoint's local `t5gemma-b-b-ul2` text encoder. When running standalone, set `AIHUB_MODELS_DIR` to the parent model folder or put the checkpoint in `apps/sound/models/`.

Generation uses the existing checkpoint offline. The first sound loads the model. Sound AI keeps it loaded until the tool stops.
