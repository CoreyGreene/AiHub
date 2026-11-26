"""Talk: talk with your local AI. It hears (Whisper), thinks (Code AI's model, through AiHub), does things (actions.py)
and answers out loud (voice.py), a sentence at a time. Also the hub's mic buttons' hearing.

    GET  /                      the Talk page (web/)
    POST /api/transcribe        a recording (the body) -> {"text"}            (the mic buttons, and Talk)
    GET  /api/voices            {voices: [{id, name, about}], voice}           the voice picker
    POST /api/voice  {id}       pick the voice (kept on this machine)
    POST /api/say    {text, voice}        that text said, as audio/wav (to hear a voice)
    POST /api/turn   {history, text, voice}  one turn, as lines of JSON as it goes (brain.py says which)
    GET  /api/listening          Always listening: {on, state, message, wake_word, log}
    POST /api/listening {on}     turn it on or off (kept on this machine)
    GET  /api/devices            {inputs, outputs, mic, speakers}: the microphones and speakers, and the ones picked
    POST /api/devices {mic, speakers}   pick them by name ("" = the Mac's default; kept on this machine)
"""

import json
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import brain, devices, ears, phrase_examples, settings, voice
from .listener import LISTENER, _wav, _words, match

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_last_talk = 0.0


@app.middleware("http")
async def fresh_page(request, call_next):
    """The page's files are checked for changes every time, so an update shows at once (no old copy)."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["cache-control"] = "no-cache"
    return response


def _unloader():
    """Let go of Whisper and the voices once nothing has been said for a while."""
    while True:
        time.sleep(30)
        if LISTENER.state in ("listening", "thinking", "speaking"):
            continue
        idle = time.time() - max(ears.last_used(), _last_talk)
        if idle > settings.get()["unload_after_minutes"] * 60:
            # listening for a wake phrase uses Whisper all the time: keep it then
            if not (LISTENER.state == "waiting" and settings.get()["wake_mode"] == "phrase"):
                ears.unload()
            voice.unload()


threading.Thread(target=_unloader, daemon=True).start()
if settings.get()["always_listening"]:
    LISTENER.start()


@app.post("/api/transcribe")
async def transcribe(request: Request) -> dict:
    data = await request.body()
    if not data:
        raise HTTPException(400, "Nothing was recorded.")
    if len(data) > settings.get()["max_mb"] * 1024 * 1024:
        raise HTTPException(400, "That recording is too long.")
    try:
        text = await _in_thread(ears.transcribe, data, request.headers.get("content-type", "audio/webm"))
    except ears.NotHeard as err:
        raise HTTPException(400, str(err))
    return {"text": text}


async def _in_thread(fn, *args):
    import anyio

    return await anyio.to_thread.run_sync(lambda: fn(*args))


@app.get("/api/voices")
def voices() -> dict:
    return {"voices": voice.voices(), "voice": settings.get()["voice"]}


class VoiceRequest(BaseModel):
    id: str


@app.post("/api/voice")
def pick_voice(req: VoiceRequest) -> dict:
    if req.id not in [v["id"] for v in voice.voices()]:
        raise HTTPException(400, "There's no voice by that name.")
    settings.set_local("voice", req.id)
    return voices()


class SayRequest(BaseModel):
    text: str
    voice: str = ""


@app.post("/api/say")
async def say(req: SayRequest):
    text = req.text.strip()[:500]
    if not text:
        raise HTTPException(400, "Nothing to say.")
    wav = await _in_thread(voice.speak, text, req.voice or settings.get()["voice"])
    return Response(wav, media_type="audio/wav")


class TurnRequest(BaseModel):
    text: str
    history: list[dict] = []
    voice: str = ""


@app.post("/api/turn")
def turn(req: TurnRequest):
    """One turn: the answer as lines of JSON as it's written and spoken. Stopping the request (the page does when
    you interrupt) stops the turn."""
    global _last_talk
    _last_talk = time.time()
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "Say something first.")
    stopped = threading.Event()

    def lines():
        global _last_talk
        try:
            for event in brain.turn(req.history[-40:], text, req.voice or settings.get()["voice"], stopped.is_set):
                _last_talk = time.time()
                yield json.dumps(event) + "\n"
        finally:
            stopped.set()

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@app.get("/api/listening")
def listening() -> dict:
    return LISTENER.status()


class ListeningRequest(BaseModel):
    on: bool


@app.post("/api/listening")
def set_listening(req: ListeningRequest) -> dict:
    settings.set_local("always_listening", req.on)
    if req.on:
        LISTENER.start()
    else:
        LISTENER.stop()
    time.sleep(0.5)
    return LISTENER.status()


@app.get("/api/devices")
def list_devices() -> dict:
    if LISTENER.state == "off":
        devices.refresh()  # read the list again (only safe with no microphone open)
    s = settings.get()
    return {**devices.listing(), "mic": s.get("mic", ""), "speakers": s.get("speakers", "")}


class DevicesRequest(BaseModel):
    mic: str = ""
    speakers: str = ""


@app.post("/api/devices")
def pick_devices(req: DevicesRequest) -> dict:
    settings.set_local("mic", req.mic)
    settings.set_local("speakers", req.speakers)
    if LISTENER.state != "off":  # open the new microphone
        LISTENER.stop()
        LISTENER.start()
        time.sleep(0.5)
    return list_devices()


@app.get("/api/phrase-examples")
def phrase_example_status() -> dict:
    s = settings.get()
    return {"phrases": {"wake": s["wake_phrase"], "end": s["end_phrase"]},
            "counts": phrase_examples.counts(s), "minimum": phrase_examples.MIN_EXAMPLES,
            "wake_mode": s["wake_mode"]}


@app.post("/api/phrase-examples/{kind}")
def record_phrase_example(kind: str, test: bool = False) -> dict:
    import sounddevice as sd

    status = phrase_example_status()
    if kind not in status["phrases"]:
        raise HTTPException(404, "Choose the wake or goodbye phrase.")
    if kind == "wake" and status["wake_mode"] != "phrase":
        raise HTTPException(409, "Voice examples for waking need phrase mode.")
    if LISTENER.status()["on"]:
        raise HTTPException(409, "Turn Always listening off before recording examples.")
    if test and status["counts"][kind] < status["minimum"]:
        raise HTTPException(409, "Record more examples before testing.")
    phrase = status["phrases"][kind]
    try:
        with sd.InputStream(device=devices.pick("input")[0], samplerate=phrase_examples.RATE,
                            channels=1, dtype="int16") as mic:
            samples, overflow = mic.read(3 * phrase_examples.RATE)
        if overflow:
            raise phrase_examples.SampleError("The recording dropped some audio. Try again.")
        if test:
            samples = samples[:, 0]
            matched = phrase_examples.matches(kind, phrase, samples)
            try:
                heard = ears.transcribe(_wav(samples), "audio/wav")
            except ears.NotHeard:
                heard = ""
            if kind == "wake":
                whisper_matched = match(heard, phrase) is not None
            else:
                aliases = settings.get()["end_phrase_aliases"]
                whisper_matched = any(_words(heard) == _words(option) for option in (phrase, *aliases))
            return {"matched": matched, "heard": heard, "whisper_matched": whisper_matched}
        phrase_examples.add(kind, phrase, samples[:, 0])
    except sd.PortAudioError as err:
        raise HTTPException(400, "Couldn't record from the selected Mac microphone.") from err
    except phrase_examples.SampleError as err:
        raise HTTPException(400, str(err)) from err
    return phrase_example_status()


@app.delete("/api/phrase-examples")
def clear_phrase_examples() -> dict:
    phrase_examples.clear()
    return phrase_example_status()


app.mount("/", StaticFiles(directory=settings.ROOT / "web", html=True), name="web")
