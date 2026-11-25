"""Hearing: a recording in, the words said in it out (Whisper through MLX). For the hub's mic buttons and Talk."""

import tempfile
import time

from . import settings, voice

_last_used = 0.0
SUFFIX = {"webm": ".webm", "mp4": ".mp4", "m4a": ".m4a", "mpeg": ".mp3", "ogg": ".ogg", "wav": ".wav", "x-wav": ".wav"}


class NotHeard(Exception):
    pass


def model_folder():
    return settings.models_folder() / settings.get()["model"]


def last_used() -> float:
    return _last_used


def transcribe(data: bytes, content_type: str = "audio/webm") -> str:
    """The words in a recording (any common format: ffmpeg reads it)."""
    global _last_used
    folder = model_folder()
    if not (folder / "config.json").is_file():
        raise NotHeard(f"The Whisper model isn't here ({folder.name}). Put it in the SoundModels folder.")
    kind = content_type.split(";")[0].split("/")[-1]
    with tempfile.NamedTemporaryFile(suffix=SUFFIX.get(kind, ".webm")) as f:
        f.write(data)
        f.flush()
        import mlx_whisper

        with voice.LOCK:
            _last_used = time.time()
            try:
                result = mlx_whisper.transcribe(f.name, path_or_hf_repo=str(folder),
                                                language=settings.get()["language"] or None,
                                                condition_on_previous_text=False)
            except Exception as err:
                raise NotHeard(f"Couldn't hear anything in that recording ({type(err).__name__}).")
            _last_used = time.time()
    return result["text"].strip()


def unload() -> None:
    from mlx_whisper.transcribe import ModelHolder

    with voice.LOCK:
        ModelHolder.model = ModelHolder.model_path = None
