// The Create tab: Generate, show progress, then the picture with Save,
// Download, Edit and Reset. Edit changes the picture by an instruction
// ("make the cloak red"), and the new one can be edited again. Advanced
// mode makes several pictures and shows them as a grid to pick from (pick-grid.js). All image work happens on the server.

import { chosenTheme, pickTheme, resetTheme } from "./theme-picker.js";
import { addPictures, finishGrid, gridProgress, startGrid } from "./pick-grid.js";
import { openViewer } from "./viewer.js";
import { setThemeWords, themeWords } from "./theme-words.js";
import { customValues, fillCustom } from "./custom.js";

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

// Advanced and Custom both make several pictures.
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
  const words = advanced && !isCustom ? themeWords() : null; // Advanced: the theme's words as changed
  const custom = isCustom ? customValues() : null;
  if (isCustom && !custom) return showNote("Custom isn't ready", "The model list didn't load. Reload the page.");
  if (adding) return addItem({ theme, prompt, count, words, custom, name: els.character.value.trim() });

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
      body: JSON.stringify({ theme, prompt, count, words, custom }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    const job = await follow(data.job, advanced);
    if (advanced && job.pictures.length) {
      // The grid is already showing them; say how it ended, if it's news.
      addPictures(job.pictures);
      const made = `${job.pictures.length} of ${job.count} pictures were made`;
      if (job.status === "failed") finishGrid(job.blocked, `Something went wrong: ${job.message} (${made}.)`);
      else finishGrid(job.blocked, job.stopped ? `Stopped: ${made}.` : "");
    } else if (job.status === "blocked") showNote("Not shown", job.message);
    else if (job.status === "removed") showNote("Removed from the queue", job.message);
    else if (job.status === "failed") showNote("Something went wrong", job.message);
    else showImage(job.pictures[0].picture, job.pictures[0].image);
  } catch (err) {
    showNote("Couldn't make the picture", err.message || "Check that the server is still running.");
  } finally {
    els.button.disabled = false;
    els.button.textContent = "Generate";
  }
}

// Ask the server how the job is going until it's finished; returns the job.
// Several pictures: the grid shows up with the first one, and each new one
// is added as it's made.
async function follow(jobId, grid) {
  let started = false;
  for (;;) {
    const res = await fetch(`api/jobs/${jobId}`);
    const job = await res.json();
    if (!res.ok) throw new Error(job.detail);
    if (grid && job.pictures.length && !started) {
      startGrid(els.result, startOver);
      started = true;
    }
    if (!["waiting", "working"].includes(job.status)) return job;
    if (started) {
      addPictures(job.pictures);
      gridProgress(...describe(job));
    } else showProgress(...describe(job));
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

// note: a line to show under it (when an edit didn't work).
function showImage(id, url, note = "") {
  pictureId = id;

  const img = document.createElement("img");
  img.className = "picture";
  img.alt = "Your picture";
  img.src = url;
  img.addEventListener("click", () => openViewer([{ image: url }], 0)); // see it big

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

  const editBox = makeEditBox(id, url);
  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "button";
  edit.textContent = "Edit";
  edit.addEventListener("click", () => {
    editBox.hidden = false;
    editBox.querySelector("textarea").focus();
  });

  const actions = document.createElement("div");
  actions.className = "actions three";
  actions.append(download, edit, reset);

  const box = document.createElement("div");
  box.className = "done";
  box.append(img, saveButton, actions, editBox);
  if (note) {
    const line = document.createElement("p");
    line.className = "error-line";
    line.textContent = note;
    box.append(line);
  }
  els.result.replaceChildren(box);
}

// --- Edit: "what should change?", then the edited picture in its place ---

function makeEditBox(id, url) {
  const box = document.createElement("div");
  box.className = "edit-box";
  box.hidden = true;
  box.innerHTML = `
    <label class="field">
      <span class="label">What should change?</span>
      <textarea rows="2" placeholder="Make the cloak red"></textarea>
      <span class="error-line" hidden>Say what to change first.</span>
    </label>
    <div class="actions">
      <button type="button" class="primary">Edit</button>
      <button type="button" class="button">Cancel</button>
    </div>`;
  const text = box.querySelector("textarea");
  const error = box.querySelector(".error-line");
  const [go, cancel] = box.querySelectorAll("button");
  text.addEventListener("input", () => (error.hidden = true));
  cancel.addEventListener("click", () => (box.hidden = true));
  go.addEventListener("click", () => {
    const instruction = text.value.trim();
    error.hidden = Boolean(instruction);
    if (instruction) runEdit(id, url, instruction);
  });
  return box;
}

async function runEdit(id, url, instruction) {
  els.button.disabled = true;
  showProgress("Sending…");
  let problem = "";
  try {
    const res = await fetch(`api/pictures/${id}/edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: instruction }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    const job = await follow(data.job, false);
    if (job.status === "done") return showImage(job.pictures[0].picture, job.pictures[0].image);
    problem = job.message;
  } catch (err) {
    problem = err.message || "Check that the server is still running.";
  } finally {
    els.button.disabled = false;
  }
  // It didn't work: the picture from before comes back, with what happened.
  showImage(id, url, `Couldn't edit: ${problem}`);
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

// Library → Copy settings: the Custom tab, filled in with everything a
// picture was made with (prompt, model, LoRAs, words, size) and
// its character, ready to tweak and Generate again.
export function startFrom(recipe) {
  els.prompt.value = recipe.prompt;
  els.promptError.hidden = true;
  els.character.value = recipe.character;
  els.characterError.hidden = true;
  const note = document.getElementById("copied-note");
  const from = recipe.character ? `a picture of ${recipe.character}` : "a saved picture";
  note.textContent =
    `Settings copied from ${from}. Change anything you like, then Generate. Each new picture still comes out a bit different.` +
    (recipe.complete ? "" : " (This picture is older, so its theme's words and settings are as they are now.)");
  note.hidden = false;
  // On Advanced with its theme (and the words it was made with), or on
  // Custom when that theme is gone or it was made there.
  if (recipe.theme) {
    pickTheme(recipe.theme);
    if (recipe.words) setThemeWords(recipe.theme, recipe.words);
    location.hash = "#create/advanced";
  } else {
    fillCustom(true, recipe.custom);
    location.hash = "#create/custom";
  }
}

// --- Add mode: the form makes a workflow item instead of pictures ---
// (workflows.js turns it on). Standard is hidden: an item has a count.

let adding = null; // { label, button, done(item) -> problem or null }
const addingBar = document.getElementById("adding-bar");
const addingError = document.getElementById("adding-error");

export function isAdding() {
  return Boolean(adding);
}

export function setAddMode(mode) {
  adding = mode;
  els.view.classList.toggle("adding", Boolean(mode));
  addingBar.hidden = !mode;
  addingError.hidden = true;
  document.getElementById("adding-text").textContent = mode?.label || "";
  els.button.textContent = mode?.button || "Generate";
  document.getElementById("character-label").textContent = mode ? "Name for these pictures" : "Character name";
  els.character.placeholder = mode ? "They go to Library → Staging under this name" : "Grim the goblin";
}

// Fill the form from an item (or clean, for a new one), on Advanced or Custom.
export function fillFromItem(item) {
  startOver();
  if (item) {
    els.prompt.value = item.prompt;
    els.character.value = item.name || "";
    setCount(item.count);
    if (item.custom) fillCustom(true, item.custom);
    else {
      pickTheme(item.theme);
      if (item.words) setThemeWords(item.theme, item.words);
    }
  }
  location.hash = item?.custom ? "#create/custom" : "#create/advanced";
}

async function addItem(item) {
  els.button.disabled = true;
  const problem = await adding.done(item).catch(() => "Couldn't save. Is the server running?");
  els.button.disabled = false;
  addingError.textContent = problem || "";
  addingError.hidden = !problem;
  if (!problem) {
    setAddMode(null);
    startOver();
  }
}

document.getElementById("adding-cancel").addEventListener("click", () => {
  setAddMode(null);
  startOver();
  location.hash = "#workflows";
});

// Back to a clean page: first theme, empty prompt, no picture.
export function startOver() {
  resetTheme();
  els.prompt.value = "";
  els.promptError.hidden = true;
  els.character.value = "";
  els.characterError.hidden = true;
  pictureId = saveButton = savedTo = null;
  addingError.hidden = true;
  els.result.innerHTML = emptyResult;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

els.form.addEventListener("submit", onGenerate);
els.prompt.addEventListener("input", () => (els.promptError.hidden = true));
els.character.addEventListener("input", () => {
  els.characterError.hidden = true;
  updateSave();
});

