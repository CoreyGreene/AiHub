"""Local acoustic examples for the Always listening phrases."""

import json
import threading
from functools import cache

import numpy as np

from . import settings

RATE = 16000
MIN_EXAMPLES = 5
MAX_EXAMPLES = 12
_PATH = settings.ROOT / "phrase-examples.local.json"
_LOCK = threading.Lock()
_WINDOW = 400
_HOP = 160
_FFT = 512
_BANDS = 26
_FRAMES = 36


class SampleError(Exception):
    pass


@cache
def _filters():
    # Triangular mel bands, followed by a cosine transform. Skip the energy coefficient.
    edges = 700 * (np.geomspace(1 + 80 / 700, 1 + 7600 / 700, _BANDS + 2) - 1)
    hz = np.fft.rfftfreq(_FFT, 1 / RATE)[:, None]
    lower = (hz - edges[:-2]) / (edges[1:-1] - edges[:-2])
    upper = (edges[2:] - hz) / (edges[2:] - edges[1:-1])
    bands = np.maximum(0, np.minimum(lower, upper))
    cepstrum = np.cos(np.pi * (np.arange(_BANDS)[:, None] + .5) * np.arange(1, 14) / _BANDS)
    return bands, cepstrum


def _signature(samples: np.ndarray) -> tuple[float, np.ndarray] | None:
    if not _WINDOW <= samples.size <= RATE * 5:
        return None
    frames = np.lib.stride_tricks.sliding_window_view(samples, _WINDOW)[::_HOP].astype(np.float32)
    frames -= frames.mean(axis=1, keepdims=True)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    level = np.convolve(rms, np.full(5, .2), mode="same")
    quiet, loud = np.percentile(level, [25, 95])
    speaking = np.flatnonzero(level >= max(120, min(quiet * 3, loud * .4), loud * .16))
    if not len(speaking):
        return None
    start, stop = max(0, speaking[0] - 3), speaking[-1] + 4
    frames = frames[start:stop]
    duration = len(frames) * _HOP / RATE
    if not .35 <= duration <= 2.5:
        return None
    spectrum = abs(np.fft.rfft(frames * np.hanning(_WINDOW), n=_FFT)) ** 2
    bands, cepstrum = _filters()
    features = np.log(np.maximum(spectrum @ bands, 1e-9)) @ cepstrum
    # Compare the progression of the sounds, allowing moderate changes in speaking pace.
    positions = np.linspace(0, len(features) - 1, _FRAMES)
    values = np.stack([np.interp(positions, np.arange(len(features)), col) for col in features.T], axis=1)
    values -= values.mean(axis=0)
    values /= max(np.linalg.norm(values), 1e-9)
    return duration, values


@cache
def _load(version: int) -> dict:
    try:
        return json.loads(_PATH.read_text())
    except FileNotFoundError:
        return {}


def _profiles():
    try:
        version = _PATH.stat().st_mtime_ns
    except FileNotFoundError:
        return {}
    return _load(version)


def _examples(kind: str, phrase: str) -> list:
    record = _profiles().get(kind, {})
    return record.get("examples", []) if record.get("phrase") == phrase else []


def counts(s: dict) -> dict:
    return {kind: len(_examples(kind, s[f"{kind}_phrase"])) for kind in ("wake", "end")}


def ready(kind: str, phrase: str) -> bool:
    return len(_examples(kind, phrase)) >= MIN_EXAMPLES


def add(kind: str, phrase: str, samples: np.ndarray) -> None:
    result = _signature(samples)
    if result is None:
        raise SampleError("Say the phrase once, clearly, with a short pause before and after it.")
    duration, values = result
    with _LOCK:
        profiles = dict(_profiles())
        examples = _examples(kind, phrase)
        if len(examples) >= MAX_EXAMPLES:
            raise SampleError("This phrase already has enough examples. Clear them to record again.")
        profiles[kind] = {"phrase": phrase, "examples": [*examples, [duration, values.round(6).tolist()]]}
        spare = _PATH.with_suffix(".saving.local.json")
        spare.write_text(json.dumps(profiles))
        spare.replace(_PATH)
        _load.cache_clear()


def clear() -> None:
    with _LOCK:
        _PATH.unlink(missing_ok=True)
        _load.cache_clear()


def _similarity(values: np.ndarray, reference: np.ndarray) -> float:
    """Compare the same sounds even when a syllable starts a little earlier or later."""
    distances = np.sum((values[:, None] - reference[None, :]) ** 2, axis=-1)
    cost = np.full((_FRAMES + 1, _FRAMES + 1), np.inf)
    cost[0, 0] = 0
    for i in range(1, _FRAMES + 1):
        for j in range(max(1, i - 6), min(_FRAMES, i + 6) + 1):
            distance = distances[i - 1, j - 1]
            cost[i, j] = min(cost[i - 1, j - 1] + 2 * distance,
                             min(cost[i - 1, j], cost[i, j - 1]) + distance + .006)
    return 1 - float(cost[-1, -1]) / 4


def matches(kind: str, phrase: str, samples: np.ndarray) -> bool:
    examples = _examples(kind, phrase)
    if len(examples) < MIN_EXAMPLES:
        return False
    result = _signature(samples)
    if result is None:
        return False
    duration, values = result
    # Require agreement with more than one example. A single bad enrollment won't trigger it.
    scores = [_similarity(values, np.asarray(reference)) for length, reference in examples
              if .72 <= duration / length <= 1.38]
    return sum(score >= .84 for score in scores) >= 2
