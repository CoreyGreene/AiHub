// The Talk page: tap Talk, and it's a conversation until you tap again. It hears when you start and stop
// speaking (the loudness of the mic), sends what you said to be written down and answered, and plays the answer a
// sentence at a time as it comes. Talking while it speaks interrupts it. All the work is on the server.

const $ = (id) => document.getElementById(id);
const button = $("talk");
const label = $("talk-label");
const stateLine = $("state");
const note = $("note");
const log = $("log");
const voiceSelect = $("voice");

const SILENCE_MS = 900;      // a pause this long after speaking ends what you said
const GIVE_UP_MS = 30000;    // nothing said for this long ends the conversation
const BARGE_MS = 300;        // speaking this long over it interrupts it

let state = "idle";          // idle, listening, thinking, speaking
let stream = null, ctx = null, analyser = null, levels = null;
let floor = 0.01;            // the room's own noise (measured at the start)
let recorder = null, chunks = [], heardAt = 0, quietSince = 0, listenStart = 0;
let history = [];            // the conversation so far (sent each turn)
let playing = [], playEnd = 0, abort = null, loudSince = 0;
let voices = [];

function setState(next, words) {
  state = next;
  button.dataset.state = next;
  label.textContent = { idle: "Talk", listening: "Listening", thinking: "Thinking", speaking: "Speaking" }[next];
  stateLine.textContent = words ?? {
    idle: "Tap to start", listening: "Go ahead, I'm listening. Tap to end.",
    thinking: "Thinking…", speaking: "Talk over it to interrupt. Tap to end.",
  }[next];
}

function show(who, text, cls = "") {
  if (log.querySelector("p.muted")) log.innerHTML = "";
  const el = document.createElement("div");
  if (who === "did") {
    el.className = "did";
    el.textContent = text;
  } else {
    el.className = `msg ${who}`;
    const name = document.createElement("span");
    name.className = "who";
    name.textContent = who === "you" ? "You" : "Octavia";
    el.append(name, document.createTextNode(text));
  }
  log.append(el);
  el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  $("clear").hidden = false;
  return el;
}

function warn(text) {
  note.textContent = text;
  note.hidden = !text;
}

// ---------- the mic ----------

function level() {
  analyser.getFloatTimeDomainData(levels);
  let sum = 0;
  for (const x of levels) sum += x * x;
  return Math.sqrt(sum / levels.length);
}

async function openMic() {
  if (stream) return true;
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    warn("The mic only works on a secure page: open Talk on the Mac (localhost) for now.");
    return false;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch {
    warn("The mic isn't allowed. Allow it for this page in the browser's settings, then tap Talk again.");
    return false;
  }
  ctx = new AudioContext();
  analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  levels = new Float32Array(analyser.fftSize);
  ctx.createMediaStreamSource(stream).connect(analyser);
  // a moment of the room, to know what quiet sounds like
  let total = 0;
  for (let i = 0; i < 10; i++) {
    await new Promise((r) => setTimeout(r, 50));
    total += level();
  }
  floor = Math.max(0.004, total / 10);
  requestAnimationFrame(watch);
  return true;
}

function closeMic() {
  stream?.getTracks().forEach((t) => t.stop());
  ctx?.close();
  stream = ctx = analyser = null;
}

const speechLevel = () => Math.max(0.015, floor * 3);
const bargeLevel = () => Math.max(0.05, floor * 6);

// Every frame: how loud it is, and what that means for where we are.
function watch() {
  if (!analyser) return;
  const now = performance.now();
  const v = level();
  button.style.setProperty("--level", Math.min(1, v / (speechLevel() * 4)).toFixed(2));

  if (state === "listening") {
    if (v > speechLevel()) {
      if (!heardAt) heardAt = now;
      quietSince = 0;
    } else if (heardAt) {
      quietSince ||= now;
      if (now - quietSince > SILENCE_MS) finishListening();
    } else if (now - listenStart > GIVE_UP_MS) {
      end("Ended: nothing said for a while. Tap to talk again.");
    }
  } else if (state === "speaking") {
    if (v > bargeLevel()) {
      loudSince ||= now;
      if (now - loudSince > BARGE_MS) interrupt();
    } else loudSince = 0;
    if (!abort && playing.length && ctx.currentTime > playEnd + 0.2) listen(); // done speaking: your turn
  }
  requestAnimationFrame(watch);
}

function listen() {
  stopPlaying();
  chunks = [];
  heardAt = quietSince = loudSince = 0;
  listenStart = performance.now();
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  recorder.start();
  setState("listening");
}

function finishListening() {
  setState("thinking", "Writing down what you said…");
  const rec = recorder;
  recorder = null;
  rec.onstop = () => heard(new Blob(chunks, { type: rec.mimeType || "audio/webm" }));
  rec.stop();
}

// ---------- a turn ----------

async function heard(blob) {
  let text = "";
  try {
    const res = await fetch("api/transcribe", { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    text = data.text.trim();
  } catch (err) {
    warn(err.message || "Couldn't write down what you said.");
  }
  if (state === "idle") return;
  if (!text || /^[\s.,!?]*$/.test(text)) return listen(); // just a noise: keep listening
  show("you", text);
  answer(text);
}

async function answer(text) {
  setState("thinking");
  warn("");
  abort = new AbortController();
  const reply = show("hub", "");
  let said = "";
  try {
    const res = await fetch("api/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, history, voice: voiceSelect.value }),
      signal: abort.signal,
    });
    if (!res.ok) throw new Error((await res.json()).detail);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, nl);
        buffer = buffer.slice(nl + 1);
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.say) {
          said += (said ? " " : "") + event.say;
          reply.lastChild.textContent = said;
          await play(event.audio);
        } else if (event.did) {
          reply.before(show("did", event.did)); // what it did, above what it says about it
        } else if (event.error) {
          warn(event.error);
        } else if (event.done) {
          history.push(...event.messages);
        }
      }
    }
  } catch (err) {
    if (err.name !== "AbortError") warn(err.message || "Something went wrong. Is Code AI's model there?");
  }
  abort = null;
  if (!said) reply.remove();
  if (state === "idle") return;
  if (!playing.length) listen(); // nothing to say (or it failed): your turn
}

// ---------- speaking ----------

async function play(b64) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const audio = await ctx.decodeAudioData(bytes.buffer);
  if (state === "idle" || state === "listening") return;
  const source = ctx.createBufferSource();
  source.buffer = audio;
  source.connect(ctx.destination);
  const start = Math.max(ctx.currentTime + 0.05, playEnd);
  source.start(start);
  playEnd = start + audio.duration;
  playing.push(source);
  setState("speaking");
}

function stopPlaying() {
  for (const s of playing) {
    try { s.stop(); } catch { /* already done */ }
  }
  playing = [];
  playEnd = 0;
}

function interrupt() {
  abort?.abort();
  abort = null;
  listen();
  heardAt = performance.now(); // you're already talking
}

// ---------- start and end ----------

async function begin() {
  warn("");
  if (!(await openMic())) return;
  await ctx.resume();
  listen();
}

function end(words) {
  abort?.abort();
  abort = null;
  if (recorder && recorder.state !== "inactive") {
    recorder.onstop = null;
    recorder.stop();
  }
  recorder = null;
  stopPlaying();
  closeMic();
  setState("idle", words);
}

button.addEventListener("click", () => (state === "idle" ? begin() : end()));
$("clear").addEventListener("click", () => {
  history = [];
  log.innerHTML = '<p class="muted">What you both say shows here.</p>';
  $("clear").hidden = true;
});

// ---------- the voice ----------

async function loadVoices() {
  const data = await fetch("api/voices").then((r) => r.json());
  voices = data.voices;
  voiceSelect.replaceChildren(...voices.map((v) => new Option(v.name, v.id)));
  voiceSelect.value = data.voice;
  showAbout();
}

function showAbout() {
  $("voice-about").textContent = voices.find((v) => v.id === voiceSelect.value)?.about || "";
}

voiceSelect.addEventListener("change", async () => {
  showAbout();
  await fetch("api/voice", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: voiceSelect.value }) });
});

$("hear").addEventListener("click", async () => {
  const b = $("hear");
  b.disabled = true;
  b.textContent = "…";
  try {
    const name = voiceSelect.selectedOptions[0]?.text || "";
    const res = await fetch("api/say", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: `Hi, I'm ${name}. What would you like to make today?`, voice: voiceSelect.value }) });
    const audio = new Audio(URL.createObjectURL(await res.blob()));
    await audio.play();
  } finally {
    b.disabled = false;
    b.textContent = "Hear it";
  }
});

// ---------- always listening (on the Mac itself) ----------

const always = $("always");
const STATE_WORDS = {
  off: "", waiting: "Waiting for the wake word", listening: "Listening to you…",
  thinking: "Thinking…", speaking: "Speaking (say the wake word to interrupt)",
};
let shownLog = 0;

async function showListening(data) {
  data ||= await fetch("api/listening").then((r) => r.json()).catch(() => null);
  if (!data) return;
  always.checked = data.on;
  $("listen-about").textContent = `On this Mac, through its own mic and speakers: say "${data.wake_word}" any time ` +
    "to start talking, no page needed. Only the wake word is listened for until then.";
  const words = STATE_WORDS[data.state] || data.state;
  $("listen-state").textContent = words ? `Now: ${words}` : "";
  $("listen-state").hidden = !words;
  $("listen-message").textContent = data.message;
  $("listen-message").hidden = !data.message;
  // what's said aloud on the Mac shows in the conversation too
  const fresh = data.log.filter((e) => e.time * 1000 > shownLog);
  for (const e of fresh) show(e.who === "you" ? "you" : e.who === "did" ? "did" : "hub", e.text);
  if (fresh.length) shownLog = fresh[fresh.length - 1].time * 1000;
}

always.addEventListener("change", async () => {
  always.disabled = true;
  const on = always.checked;
  try {
    const data = await fetch("api/listening", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on }) }).then((r) => r.json());
    // the hub starts Talk with itself while it's on, so it's always listening while Ai-Hub runs
    await fetch(`/hub/api/apps/talk/autostart`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on }) }).catch(() => {});
    showListening(data);
  } finally {
    always.disabled = false;
  }
});

setState("idle");
loadVoices();
shownLog = Date.now();
showListening();
setInterval(showListening, 2000);
