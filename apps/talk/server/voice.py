"""Speaking: text in, a .wav out, in one of the voices in settings.json ("voices"), through mlx-audio.

Each voice model (Kokoro, Qwen3-TTS) is loaded the first time one of its voices speaks and kept until Talk has
been quiet for a while (app.py lets go of it with the rest). Only one thing uses the graphics at a time (the lock).
"""

import io
import os
import threading
import wave

os.environ["HF_HUB_OFFLINE"] = "1"  # every model is a local folder: never download

import numpy as np

from . import settings

LOCK = threading.Lock()  # one MLX job at a time: speaking and listening share the graphics
_models: dict[str, object] = {}


def voices() -> list[dict]:
    """The voices to pick from: [{id, name, about}], only those whose model is here."""
    folder = settings.models_folder()
    return [{"id": v["id"], "name": v["name"], "about": v.get("about", "")}
            for v in settings.get()["voices"] if (folder / v["model"] / "config.json").is_file()]


def _voice(voice_id: str) -> dict:
    found = next((v for v in settings.get()["voices"] if v["id"] == voice_id), None)
    return found or settings.get()["voices"][0]


def _model(folder_name: str):
    if folder_name not in _models:
        from mlx_audio.tts.utils import load_model

        _models[folder_name] = load_model(str(settings.models_folder() / folder_name))
    return _models[folder_name]


def unload() -> None:
    with LOCK:
        _models.clear()
        try:
            import mlx.core as mx

            mx.clear_cache()
        except (ImportError, AttributeError):
            pass


def speak(text: str, voice_id: str) -> bytes:
    """The text said in that voice, as a 16-bit .wav."""
    v = _voice(voice_id)
    kw = {"voice": v["voice"]}
    if v.get("lang_code"):
        kw["lang_code"] = v["lang_code"]
    if v.get("instruct"):
        kw["instruct"] = v["instruct"]
    with LOCK:
        model = _model(v["model"])
        audio = np.concatenate([np.array(r.audio, dtype=np.float32) for r in model.generate(text=text, **kw)])
        rate = model.sample_rate
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return out.getvalue()
