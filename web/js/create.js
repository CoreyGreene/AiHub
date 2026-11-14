// The Create tab: Generate, show progress, then the picture with Save,
// Download and Reset. All image work happens on the server.

import { chosenTheme, resetTheme } from "./theme-picker.js";

const els = {
  form: document.getElementById("make"),
  prompt: document.getElementById("prompt"),
  promptError: document.getElementById("prompt-error"),
  character: document.getElementById("character"),
  characterError: document.getElementById("character-error"),
  button: document.getElementById("generate"),
  result: document.getElementById("result"),
};

const emptyResult = els.result.innerHTML; // "Your picture will show up here."
const POLL_MS = 700;

function showNote(title, text) {
  const note = document.createElement("p");
  note.className = "note";
  const strong = document.createElement("strong");
  strong.textContent = title;
  note.append(strong, text);
  els.result.replaceChildren(note);
}

// --- Generate: the server queues the picture; we ask how it's going. ---

async function onGenerate(event) {
  event.preventDefault();
  const theme = chosenTheme()?.id;
  const prompt = els.prompt.value.trim();

  if (!theme) return showNote("Pick a theme first", "");
  // Shown right under the box (not in the result area, which the phone
  // keyboard can hide).
  els.promptError.hidden = Boolean(prompt);
  if (!prompt) return;

  // Close the phone keyboard and bring the result area into view.
  document.activeElement?.blur();
  els.button.disabled = true;
  els.button.textContent = "Working…";
  showProgress("Sending…");
  els.result.scrollIntoView({ behavior: "smooth", block: "center" });
  try {
    const res = await fetch("api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme, prompt }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    await follow(data.job);
  } catch (err) {
    showNote("Couldn't make the picture", err.message || "Check that the server is still running.");
  } finally {
    els.button.disabled = false;
    els.button.textContent = "Generate";
  }
}

async function follow(jobId) {
  for (;;) {
    const res = await fetch(`api/jobs/${jobId}`);
    const job = await res.json();
    if (!res.ok) throw new Error(job.detail);

    if (job.status === "done") return showImage(job.picture, job.image);
    if (job.status === "blocked") return showNote("Not shown", job.message);
    if (job.status === "failed") return showNote("Something went wrong", job.message);
    showProgress(...describe(job));
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
}

// What to say while waiting, and how full the bar is (0..1, or null).
function describe(job) {
  if (job.status === "waiting") {
    return job.ahead ? [`Waiting: ${job.ahead} picture${job.ahead > 1 ? "s" : ""} ahead…`, null] : ["Starting…", null];
  }
  if (job.stage === "loading") return ["Loading the model (the first picture takes a little longer)…", null];
  if (job.stage === "drawing" && job.steps) {
    return [`Generating your image… step ${job.step} of ${job.steps}`, job.step / job.steps];
  }
  if (job.stage === "checking") return ["Checking the picture…", 1];
  return ["Generating your image…", null];
}

function showProgress(text, fraction = null) {
  let box = els.result.querySelector(".working");
  if (!box) {
    box = document.createElement("div");
    box.className = "working";
    box.innerHTML = `<div class="spinner" aria-hidden="true"></div><p></p><div class="bar" hidden><span></span></div>`;
    els.result.replaceChildren(box);
  }
  box.querySelector("p").textContent = text;
  const bar = box.querySelector(".bar");
  bar.hidden = fraction === null;
  if (fraction !== null) bar.firstElementChild.style.width = `${Math.round(fraction * 100)}%`;
}

// --- The finished picture ---

let pictureId = null; // the picture on screen now
let saveButton = null;
let savedTo = null; // character it was last saved to
let saving = false;

function showImage(id, url) {
  pictureId = id;

  const img = document.createElement("img");
  img.className = "picture";
  img.alt = "Your picture";
  img.src = url;

  saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "primary";
  saveButton.addEventListener("click", onSave);
  savedTo = null;
  updateSave();

  const download = document.createElement("a");
  download.className = "button";
  download.href = `${url}?download=1`;
  download.download = "";
  download.textContent = "Download";

  const reset = document.createElement("button");
  reset.type = "button";
  reset.className = "button";
  reset.textContent = "Reset";
  reset.addEventListener("click", startOver);

  const actions = document.createElement("div");
  actions.className = "actions";
  actions.append(download, reset);

  const box = document.createElement("div");
  box.className = "done";
  box.append(img, saveButton, actions);
  els.result.replaceChildren(box);
}

// Saving needs a character name; downloading doesn't. So Save stays
// greyed out until a name is typed.
function updateSave() {
  if (!saveButton) return;
  const name = els.character.value.trim();
  if (saving) {
    saveButton.textContent = "Saving…";
  } else if (!name) {
    saveButton.textContent = "Type a name to save";
  } else if (name === savedTo) {
    saveButton.textContent = `Saved to ${savedTo} ✓`;
  } else {
    saveButton.textContent = "Save";
  }
  saveButton.disabled = saving || !name || name === savedTo;
}

async function onSave() {
  const character = els.character.value.trim();
  saving = true;
  updateSave();
  try {
    const res = await fetch(`api/pictures/${pictureId}/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ character }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    savedTo = character;
  } catch (err) {
    els.characterError.textContent = err.message || "Couldn't save. Is the server running?";
    els.characterError.hidden = false;
  } finally {
    saving = false;
    updateSave();
  }
}

// Back to a clean page: first theme, empty prompt, no picture.
function startOver() {
  resetTheme();
  els.prompt.value = "";
  els.promptError.hidden = true;
  els.character.value = "";
  els.characterError.hidden = true;
  pictureId = saveButton = savedTo = null;
  els.result.innerHTML = emptyResult;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

els.form.addEventListener("submit", onGenerate);
els.prompt.addEventListener("input", () => (els.promptError.hidden = true));
els.character.addEventListener("input", () => {
  els.characterError.hidden = true;
  updateSave();
});
