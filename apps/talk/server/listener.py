"""Always listening, on this Mac: Talk waits for the wake word through the Mac's own microphone, then holds a
conversation out of its speakers, with no page open.

  waiting    listening for the wake phrase, one of two ways (wake_mode):
             "phrase": a short stretch of speech (a few seconds at most) is written down by Whisper on this Mac and
                       checked for the phrase (wake_phrase), then thrown away. Any phrase works, and the rest of what
                       was said in the same breath is the first question ("Hello Octavia, what's running?").
             "model":  a wake word model (openWakeWord, a few MB, on the processor), for "Hey Jarvis".
             Nothing said is kept or sent.
  listening  after the wake word (a chime), what you say is recorded until you pause
  thinking   written down (Whisper) and answered (brain.py), a sentence at a time
  speaking   played through the speakers; saying the wake word again stops it and listens
After an answer it listens a little longer for a follow-up without the wake word. The end phrase
returns it to waiting immediately.
"""

import io
import queue
import threading
import time
import wave
from collections import deque

import numpy as np

from . import brain, devices, ears, phrase_examples, settings

RATE = 16000
FRAME = 1280  # 80 ms, what the wake word model reads at a time


class Listener:
    def __init__(self):
        self.state = "off"
        self.message = ""
        self.log: list[dict] = []  # the latest exchanges, for the page: {who, text}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._frames: queue.Queue = queue.Queue(maxsize=500)
        self._floor = 200.0  # the room's own loudness (int16 RMS), followed while waiting
        self._wake_checks = 0
        self._wake_result = ""

    # ---------- on and off ----------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.message = ""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.state = "off"

    def status(self) -> dict:
        s = settings.get()
        said = s["wake_phrase"] if s["wake_mode"] == "phrase" else s["wake_word_said"]
        return {"on": self.state != "off", "state": self.state, "message": self.message,
                "wake_word": said, "end_phrase": s["end_phrase"], "end_phrase_aliases": s["end_phrase_aliases"],
                "wake_checks": self._wake_checks, "last_wake_result": self._wake_result, "log": self.log[-20:]}

    def _speech_gate(self, s: dict, kind: str) -> float:
        minimum = s["speech_level"]
        if phrase_examples.ready(kind, s[f"{kind}_phrase"]):
            minimum = min(minimum, 150)
        return max(minimum, self._floor * 3)

    def _note(self, who: str, text: str) -> None:
        self.log.append({"who": who, "text": text, "time": time.time()})
        del self.log[:-40]

    # ---------- the loop ----------

    def _run(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as err:
            self.message = f"Always listening needs its packages ({err.name}): python3 start.py installs them."
            self.state = "off"
            return
        s = settings.get()
        try:
            waker = PhraseWaker(self) if s["wake_mode"] == "phrase" else ModelWaker()
        except WakeError as err:
            self.message = str(err)
            self.state = "off"
            return

        def heard(indata, frames, when, status):  # the microphone's own thread: hand the frames over
            try:
                self._frames.put_nowait(indata[:, 0].copy())
            except queue.Full:
                pass

        # Open the microphone (the one picked: devices.py), listen, and if it goes away (unplugged, or another
        # device plugged in under it), open it again: Always listening stays on.
        while not self._stop.is_set():
            devices.refresh()
            mic, note = devices.pick("input")
            try:
                stream = sd.InputStream(device=mic, samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME,
                                        callback=heard)
                stream.start()
            except Exception as err:
                self.state = "waiting"
                self.message = f"Waiting for a microphone ({err}). Trying again every 5 seconds."
                self._stop.wait(5)
                continue
            self.message = note
            self.state = "waiting"
            try:
                self._listen(stream, waker)
            finally:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            if not self._stop.is_set():
                self.message = "The microphone went away: opening it again…"
                self._stop.wait(2)
        self.state = "off"

    def _listen(self, stream, waker) -> None:
        """Wait for the wake phrase until stopped, or until the microphone stops sending (it went away)."""
        silent_since = last_frame = time.time()
        while not self._stop.is_set():
            frame = self._get()
            if frame is None:
                if not stream.active or time.time() - last_frame > 3:
                    return
                continue
            last_frame = time.time()
            rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
            # a microphone macOS hasn't allowed gives pure silence: say so
            if rms > 0:
                silent_since = time.time()
                if self.message.startswith("The Mac"):
                    self.message = ""
            elif time.time() - silent_since > 4:
                self.message = ("The Mac isn't letting Talk use the microphone. Allow it in System Settings → "
                                "Privacy & Security → Microphone for the app Ai-Hub runs in (for example "
                                "Terminal), then turn Always listening off and on.")
            self._floor = 0.98 * self._floor + 0.02 * min(rms, self._floor * 3 + 50)
            woke = waker.feed(frame, rms)
            if woke is not None:
                waker.reset()
                self._conversation(waker, woke)
                waker.reset()
                self.state = "waiting"
                last_frame = time.time()

    def _get(self, timeout: float = 0.5):
        try:
            return self._frames.get(timeout=timeout)
        except queue.Empty:
            return None

    def _drain(self) -> None:
        while not self._frames.empty():
            self._frames.get_nowait()

    # ---------- a conversation ----------

    def _conversation(self, waker, first: str = "") -> None:
        """first: what was said in the same breath as the wake phrase (asked straight away), or ""."""
        s = settings.get()
        _chime(up=True)
        self._drain()
        history: list[dict] = []
        end_phrases = {tuple(_words(phrase)) for phrase in (s["end_phrase"], *s["end_phrase_aliases"])}
        end_phrases.discard(())
        wait_for = s["first_words_seconds"]
        while not self._stop.is_set():
            audio = None
            if first:
                # said with the wake phrase in one breath; a short pause may come before the rest
                # ("add this to the game notes, ... the jetpack is too loud"): listen a moment for more
                text, first = first, ""
                more = self._record(s["carry_on_seconds"])
                if more is not None:
                    try:
                        text = f"{text} {ears.transcribe(_wav(more), 'audio/wav')}".strip()
                    except ears.NotHeard:
                        pass
                self.state = "thinking"
            else:
                self.state = "listening"
                audio = self._record(wait_for)
                if audio is None:
                    break
                self.state = "thinking"
                try:
                    text = ears.transcribe(_wav(audio), "audio/wav")
                except ears.NotHeard as err:
                    self.message = str(err)
                    break
            if s["wake_mode"] == "phrase":  # "Hello Octavia, ..." said again as a follow-up: the rest is the question
                rest = match(text, s["wake_phrase"])
                if rest is not None:
                    text = rest
            words = tuple(_words(text))
            if words in end_phrases or (
                audio is not None and len(words) <= 3 and
                phrase_examples.matches("end", s["end_phrase"], audio)
            ):
                self._note("you", text if words in end_phrases else s["end_phrase"])
                break
            if not text.strip(" .,!?"):
                wait_for = s["follow_up_seconds"]
                continue
            self._note("you", text)
            said = []
            for event in brain.turn(history[-40:], text, s["voice"], self._stop.is_set):
                if "say" in event:
                    said.append(event["say"])
                    self.state = "speaking"
                    cut_in = self._play(event["audio"], waker)
                    if cut_in is not None:  # the wake phrase over it: stop, and what came after it is next
                        self._note("hub", " ".join(said) + " …")
                        said = []
                        first = cut_in
                        break
                elif "did" in event:
                    self._note("did", event["did"])
                elif "error" in event:
                    self.message = event["error"]
                elif "done" in event:
                    history += event["messages"]
            if said:
                self._note("hub", " ".join(said))
            self._drain()
            wait_for = s["follow_up_seconds"]
        _chime(up=False)
        self._drain()

    def _record(self, wait_seconds: float):
        """What's said next, until a pause; None if nothing is said in wait_seconds."""
        s = settings.get()
        start = time.time()
        loud = self._speech_gate(s, "end")
        frames, heard_at, quiet_for = [], None, 0.0
        while not self._stop.is_set():
            frame = self._get()
            if frame is None:
                continue
            rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
            if heard_at is None:
                frames = (frames + [frame])[-4:]  # keep a moment before it, so the first word isn't cut
                if rms > loud:
                    heard_at = time.time()
                elif time.time() - start > wait_seconds:
                    return None
                continue
            frames.append(frame)
            quiet_for = quiet_for + FRAME / RATE if rms < loud else 0.0
            if quiet_for > s["pause_seconds"] or time.time() - heard_at > s["longest_seconds"]:
                return np.concatenate(frames)
        return None

    def _play(self, b64: str, waker) -> str | None:
        """Play a sentence through the speakers, listening for the wake phrase meanwhile. If it's said, stop and
        give back what was said after it ("" if nothing); else None."""
        import base64

        import sounddevice as sd

        with wave.open(io.BytesIO(base64.b64decode(b64))) as w:
            rate = w.getframerate()
            data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        sd.play(data, rate, device=devices.pick("output")[0])
        end = time.time() + len(data) / rate
        while time.time() < end and not self._stop.is_set():
            frame = self._get(timeout=0.1)
            if frame is None:
                continue
            rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
            woke = waker.feed(frame, rms)
            if woke is not None:
                sd.stop()
                waker.reset()
                _chime(up=True)
                self._drain()
                return woke
        sd.wait()
        return None


class WakeError(Exception):
    pass


class ModelWaker:
    """A wake word model (openWakeWord): wake_word in models_dir/openWakeWord."""

    def __init__(self):
        from openwakeword.model import Model

        s = settings.get()
        folder = settings.models_folder() / "openWakeWord"
        wake = folder / f"{s['wake_word']}.onnx"
        if not wake.is_file():
            raise WakeError(f"The wake word model isn't here ({wake.name} in SoundModels/openWakeWord).")
        self.model = Model(wakeword_models=[str(wake)], melspec_model_path=str(folder / "melspectrogram.onnx"),
                           embedding_model_path=str(folder / "embedding_model.onnx"), inference_framework="onnx")
        self.name = next(iter(self.model.models))

    def feed(self, frame, rms: float) -> str | None:
        return "" if self.model.predict(frame)[self.name] >= settings.get()["wake_threshold"] else None

    def reset(self) -> None:
        self.model.reset()


class PhraseWaker:
    """The wake phrase, checked by Whisper: short stretches of speech are written down and matched (loosely, so
    "Hello, Octavia." and "hello octavia" both count), then thrown away."""

    def __init__(self, listener: "Listener"):
        if not (ears.model_folder() / "config.json").is_file():
            raise WakeError("The wake phrase needs Whisper in the SoundModels folder.")
        self.listener = listener
        self.reset()

    def reset(self) -> None:
        self.frames, self.quiet = [], 0.0
        self.lead = deque(maxlen=5)

    def feed(self, frame, rms: float) -> str | None:
        """None until the phrase is heard; then what came after it in the same breath ("" if nothing)."""
        s = settings.get()
        loud = self.listener._speech_gate(s, "wake")
        if not self.frames:
            if rms > loud:
                self.frames = [*self.lead, frame]
            else:
                self.lead.append(frame)
            return None
        self.frames.append(frame)
        self.quiet = self.quiet + FRAME / RATE if rms < loud else 0.0
        seconds = len(self.frames) * FRAME / RATE
        if seconds > s["wake_longest_seconds"]:  # a long stretch of talk: not someone waking it
            self.reset()
            return None
        if self.quiet < s["wake_pause_seconds"]:
            return None
        audio = np.concatenate(self.frames)
        self.reset()
        if seconds - s["wake_pause_seconds"] < 0.35:  # a click or a cough
            return None
        self.listener._wake_checks += 1
        try:
            text = ears.transcribe(_wav(audio), "audio/wav")
        except ears.NotHeard:
            text = ""
        rest = match(text, s["wake_phrase"])
        if rest is not None:
            self.listener._wake_result = "whisper"
            return rest
        if len(_words(text)) <= 3 and phrase_examples.matches("wake", s["wake_phrase"], audio):
            self.listener._wake_result = "voice examples"
            return ""
        self.listener._wake_result = "no match"
        return None


def _words(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9']+", text.lower())


def match(text: str, phrase: str) -> str | None:
    """If text has the phrase (near enough: Whisper may spell a name a little differently), what comes after it."""
    from difflib import SequenceMatcher

    words, want = _words(text), _words(phrase)
    if not want:
        return None
    goal = " ".join(want)
    for i in range(len(words)):
        for n in (len(want) - 1, len(want), len(want) + 1):
            if n < 1 or i + n > len(words):
                continue
            if SequenceMatcher(None, " ".join(words[i:i + n]), goal).ratio() >= 0.8:
                rest = text.split()
                # what came after it, as it was written (Whisper's own words and punctuation)
                after = " ".join(rest[i + n:]) if len(rest) == len(words) else " ".join(words[i + n:])
                return after.strip(" ,.!?")
    return None


def _wav(samples: np.ndarray) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.astype("<i2").tobytes())
    return out.getvalue()


def _chime(up: bool) -> None:
    """Two soft notes: rising when it starts listening, falling when it stops."""
    import sounddevice as sd

    rate = 24000
    notes = (660, 880) if up else (880, 587)
    t = np.arange(int(rate * 0.09)) / rate
    fade = np.minimum(1, np.minimum(t, t[::-1]) * 60)
    tone = np.concatenate([0.18 * np.sin(2 * np.pi * f * t) * fade for f in notes]).astype(np.float32)
    sd.play(tone, rate, device=devices.pick("output")[0])
    sd.wait()


LISTENER = Listener()
