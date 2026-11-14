// The Create tab: Generate, show progress, then the picture with Save,
// Download and Reset. Advanced mode makes several pictures and shows them
// as a grid to pick from (pick-grid.js). All image work happens on the server.

import { chosenTheme, resetTheme } from "./theme-picker.js";
import { showGrid } from "./pick-grid.js";
import { chosenOptions, loadOptions } from "./options.js";
import { customValues } from "./custom.js";

const els = {
  form: document.getElementById("make"),
  prompt: document.getElementById("prompt"),
  promptError: document.getElementById("prompt-error"),
  character: document.getElementById("character"),
  characterError: document.getElementById("character-error"),
  button: document.getElementById("generate"),
  result: document.getElementById("result"),
  view: document.getElementById("view-create"),
  count: document.getElementById("count"),
  countDown: document.getElementById("count-down"),
  countUp: document.getElementById("count-up"),
};

const emptyResult = els.result.innerHTML; // "Your picture will show up here."
const POLL_MS = 700;

// Advanced and Custom both make several pictures, with the options.
function isAdvanced() {
  return els.view.dataset.mode !== "standard";
}

// How many pictures (Advanced): kept between 1 and the server's limit.
function setCount(n) {
  const most = Number(els.count.max);
  els.count.value = Math.min(most, Math.max(1, Math.round(Number(n)) || 1));
}
els.countDown.addEventListener("click", () => setCount(Number(els.count.value) - 1));
els.countUp.addEventListener("click", () => setCount(Number(els.count.value) + 1));
els.count.addEventListener("change", () => setCount(els.count.value));
fetch("api/settings")
  .then((res) => res.json())
  .then((data) => {
    els.count.max = data.max_pictures;
    setCount(els.count.value);
  })
  .catch(() => {});

export function showNote(title, text) {
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
  const isCustom = els.view.dataset.mode === "custom";
  const theme = isCustom ? "" : chosenTheme()?.id; // Custom is its own theme
  const prompt = els.prompt.value.trim();

  if (!theme && !isCustom) return showNote("Pick a theme first", "");
  // Shown right under the box (not in the result area, which the phone
  // keyboard can hide).
  els.promptError.hidden = Boolean(prompt);
  if (!prompt) return;

  const advanced = isAdvanced();
  const count = advanced ? Number(els.count.value) : 1;
  const options = advanced ? chosenOptions() : {};
  const custom = isCustom ? customValues() : null;
  if (isCustom && !custom) return showNote("Custom isn't ready", "The model list didn't load. Reload the page.");

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
      body: JSON.stringify({ theme, prompt, count, options, custom }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    const job = await follow(data.job);
    if (job.status === "blocked") showNote("Not shown", job.message);
    else if (job.status === "removed") showNote("Removed from the queue", job.message);
    else if (job.status === "failed") showNote("Something went wrong", job.message);
    else if (advanced) showGrid(els.result, job.pictures, job.blocked, startOver);
    else showImage(job.pictures[0].picture, job.pictures[0].image);
  } catch (err) {
    showNote("Couldn't make the picture", err.message || "Check that the server is still running.");
  } finally {
    els.button.disabled = false;
    els.button.textContent = "Generate";
  }
}

// Ask the server how the job is going until it's finished; returns the job.
async function follow(jobId) {
  for (;;) {
    const res = await fetch(`api/jobs/${jobId}`);
    const job = await res.json();
    if (!res.ok) throw new Error(job.detail);
    if (!["waiting", "working"].includes(job.status)) return job;
    showProgress(...describe(job));
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
}

// What to say while waiting, and how full the bar is (0..1, or null).
function describe(job) {
  if (job.status === "waiting") {
    return job.ahead ? [`Waiting: ${job.ahead} picture job${job.ahead > 1 ? "s" : ""} ahead…`, null] : ["Starting…", null];
  }
  // With several pictures: "Picture 2 of 4 · ", and the bar covers all of them.
  const many = job.count > 1;
  const which = many ? `Picture ${job.number} of ${job.count} · ` : "";
  const done = (job.number - 1) / job.count;
  if (job.stage === "loading") return ["Loading the model (the first picture takes a little longer)…", null];
  if (job.stage === "drawing" && job.steps) {
    const text = many ? `${which}step ${job.step} of ${job.steps}` : `Generating your image… step ${job.step} of ${job.steps}`;
    return [text, done + job.step / job.steps / job.count];
  }
  if (job.stage === "checking") return [`${which}Checking the picture…`, done + 1 / job.count];
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
export function startOver() {
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

loadOptions();
