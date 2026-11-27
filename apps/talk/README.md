# Talk

Talk with your local AI, out loud, on your Mac. It hears you (Whisper), thinks with Code AI's model (Gemma 4, with
thinking off so it answers at once), does things when asked, and answers in a voice you pick, a sentence at a time
so it starts speaking within a second or two. It's one of the tools in AiHub (`apps/talk`), and it's also the
hearing behind the 🎤 buttons on every prompt box.

## Two ways to talk

- **The Talk page:** tap Talk and talk. It hears when you stop, answers, then listens again; talk over it to
  interrupt it; tap to end. The mic works on a secure page, so for now on the Mac itself (`localhost`).
- **Always listening:** a switch on the page. Talk then listens on the Mac through its own microphone for the wake
  phrase (`wake_phrase`, "Hello Octavia": short stretches of speech are checked by Whisper; or a wake word model,
  `wake_mode`) and answers out of its speakers, no page needed. "Hello Octavia, what's running?" works in one
  breath. Nothing said is kept until it hears the wake phrase. After the wake word: a chime, what
  you say, its answer, and it waits a few seconds for a follow-up before a falling chime. Say "Goodbye Octavia"
  or "Bye Octavia" on its own while Talk is listening to end the conversation early and go back to waiting for
  "Hello Octavia".
  Saying the wake word while
  it talks stops it. While it's on, AiHub starts Talk with itself.
- **Train wake and goodbye phrases:** turn Always listening off, then open the training section on the
  Talk page. Record at least five examples of each phrase you want to train. Use Test phrase with a new
  recording, then turn Always listening back on. Talk compares short recordings with your examples
  when the transcript misses the phrase. The examples are stored locally as sound features.

## What it can do when asked

Say what's running and the Mac's memory; **the lights** through Lights AI: "turn off the fireplace and stair lights", "dim Main 3 to 40", "make all the lights warm", "are any lights on?"; start or stop Image AI, 3D AI, Code AI or Movie AI; make a picture (with a
theme) or a video; say how the queues are going; **take notes**: "add to my grocery notes: milk and eggs" adds a
line (with the time, under the day) to that name's file, `notes_folder/grocery.md`, made when first used ("make a
note: ..." with no name: `notes.md`). "What notes do I have?" lists them; "what's in my game notes?" reads them
back. `notes` in `server/settings.local.json` can send a name elsewhere (e.g. game → the game's
`docs/playtest-notes.md`, so Claude can later turn them into tasks). Each action is a small function in
`server/actions.py`.

## Voices

`voices` in `server/settings.json`: each names a model folder in SoundModels and its voice. Kokoro (82M, the
quickest) and Qwen3-TTS 1.7B CustomVoice (natural; takes a tone, like "warm and friendly"), through mlx-audio.
The page's picker saves the one used.

## How it's built

- `server/app.py`: the routes (listed at its top). `server/ears.py`: Whisper. `server/voice.py`: the voices.
- `server/thinker.py`: keeps Code AI's model loaded while Talk runs, so answers never wait for it to load. Talk starts Code AI and loads it when Talk starts, and renews the hold every minute; anything else may still let it go. If a bigger model is loaded, the Talk page asks before replacing it.
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
