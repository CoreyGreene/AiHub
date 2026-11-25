# Talk

Talk with your local AI, out loud, on your Mac. It hears you (Whisper), thinks with Code AI's model (Gemma 4, with
thinking off so it answers at once), does things when asked, and answers in a voice you pick, a sentence at a time
so it starts speaking within a second or two. It's one of the tools in AiHub (`apps/talk`), and it's also the
hearing behind the 🎤 buttons on every prompt box.

## Two ways to talk

- **The Talk page:** tap Talk and talk. It hears when you stop, answers, then listens again; talk over it to
  interrupt it; tap to end. The mic works on a secure page, so for now on the Mac itself (`localhost`).
- **Always listening:** a switch on the page. Talk then listens on the Mac through its own microphone for the wake
  word (`wake_word_said`, "Hey Jarvis" for now) and answers out of its speakers, no page needed. Until it hears
  the wake word only the tiny wake word model runs, and nothing said is kept. After the wake word: a chime, what
  you say, its answer, and it waits a few seconds for a follow-up before a falling chime. Saying the wake word while
  it talks stops it. While it's on, AiHub starts Talk with itself.

## What it can do when asked

Say what's running and the Mac's memory; start or stop Image AI, 3D AI, Code AI or Movie AI; make a picture (with a
theme) or a video; say how the queues are going. Each is a small function in `server/actions.py` that calls AiHub.

## Voices

`voices` in `server/settings.json`: each names a model folder in SoundModels and its voice. Kokoro (82M, the
quickest) and Qwen3-TTS 1.7B CustomVoice (natural; takes a tone, like "warm and friendly"), through mlx-audio.
The page's picker saves the one used.

## How it's built

- `server/app.py`: the routes (listed at its top). `server/ears.py`: Whisper. `server/voice.py`: the voices.
- `server/brain.py`: one turn. It streams the answer from Code AI's `/api/chat` through AiHub, speaks each sentence
  as soon as it's complete, and runs the actions the model asks for.
- `server/listener.py`: Always listening (sounddevice for the mic and speakers, openWakeWord for the wake word).
- `web/`: the page (plain HTML, CSS and JS).
- Models (in AiHub's `SoundModels`): Whisper, the voices, and `openWakeWord/` (the wake word and its two helpers).
  Nothing is downloaded while it runs.

## On its own

```bash
python3 start.py      # http://127.0.0.1:8500; it needs AiHub (hub_url in settings) to think and do things
```
