// Advanced results: a grid of videos, shown as each one is made (the
// progress line stays on top until the last). Tap a video to see it big
// (and pick it there); tap its tick to pick it. Then save the picked ones
// to a character. Each video has its own Download; on a computer there's
// also "Download selected" (one zip file). Phones don't get the bulk
// option: one download per video.

import { openViewer, refreshViewer } from "./viewer.js";

const character = document.getElementById("character");
const characterError = document.getElementById("character-error");

let tiles = []; // { id, file, poster, picked, savedTo, el }
let saveButton = null;
let bulkButton = null;
let countLine = null;
let saving = false;
let grid = null;
let progress = null; // the "Video 2 of 4" line while more are coming
let notes = null;

// The empty grid, with the progress line; videos are added as they come.
export function startGrid(result, onReset) {
  tiles = [];
  const box = document.createElement("div");
  box.className = "picks";

  progress = document.createElement("div");
  progress.className = "grid-working";
  progress.innerHTML = `<div class="spinner small-spinner" aria-hidden="true"></div><p class="small"></p><div class="bar"><span></span></div>`;
  notes = document.createElement("div");

  // Picked count with Select all / none.
  const bar = document.createElement("div");
  bar.className = "pick-bar";
  countLine = document.createElement("span");
  countLine.className = "muted";
  const all = textButton("Select all", () => pickAll(true));
  const none = textButton("None", () => pickAll(false));
  bar.append(countLine, all, none);
  const help = document.createElement("p");
  help.className = "muted small pick-help";
  help.textContent = "Tap a video to see it big. Tap its tick to pick it.";

  grid = document.createElement("div");
  grid.className = "pick-grid";

  saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "primary";
  saveButton.addEventListener("click", savePicked);

  bulkButton = document.createElement("button");
  bulkButton.type = "button";
  bulkButton.className = "button bulk-download";
  bulkButton.addEventListener("click", downloadPicked);

  const reset = document.createElement("button");
  reset.type = "button";
  reset.className = "button";
  reset.textContent = "Reset";
  reset.addEventListener("click", () => {
    tiles = [];
    saveButton = bulkButton = grid = null;
    onReset();
  });

  const actions = document.createElement("div");
  actions.className = "actions";
  actions.append(bulkButton, reset);

  box.append(progress, notes, bar, help, grid, saveButton, actions);
  result.replaceChildren(box);
  update();
}

// The job's videos so far: any new ones are added to the grid.
export function addVideos(videos) {
  if (!grid) return;
  for (const p of videos.slice(tiles.length)) {
    const tile = { id: p.video, file: p.file, poster: p.poster, picked: false, savedTo: null };
    tiles.push(tile);
    grid.append(tileFor(tile, tiles.length - 1));
  }
  update();
  refreshViewer();
}

export function gridProgress(text, fraction) {
  if (!progress) return;
  progress.querySelector("p").textContent = text;
  const bar = progress.querySelector(".bar");
  bar.hidden = fraction === null;
  if (fraction !== null) bar.firstElementChild.style.width = `${Math.round(fraction * 100)}%`;
}

// All made: take the progress line away; say what was left out, if anything.
export function finishGrid(blocked, message = "") {
  progress?.remove();
  progress = null;
  const lines = [];
  if (blocked) lines.push(`${blocked} video${blocked > 1 ? "s" : ""} didn't pass the safety check and ${blocked > 1 ? "were" : "was"} left out.`);
  if (message) lines.push(message);
  notes.replaceChildren(
    ...lines.map((text) => Object.assign(document.createElement("p"), { className: "note small", textContent: text }))
  );
}

function textButton(text, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "link-button";
  b.textContent = text;
  b.addEventListener("click", onClick);
  return b;
}

// Big view: the Pick button there picks the same tile.
const pickInViewer = {
  isPicked: (i) => tiles[i].picked,
  toggle: (i) => {
    tiles[i].picked = !tiles[i].picked;
    update();
  },
};

function tileFor(tile, i) {
  const item = document.createElement("div");
  item.className = "pick";

  // The video (playing, muted, on a loop) opens the big view; the tick in
  // its corner picks it.
  const frame = document.createElement("div");
  frame.className = "pick-frame";
  const open = document.createElement("button");
  open.type = "button";
  open.className = "pick-toggle";
  open.setAttribute("aria-label", `See video ${i + 1} big`);
  open.innerHTML = `<video muted loop autoplay playsinline></video><span class="saved-tag"></span>`;
  Object.assign(open.querySelector("video"), { src: tile.file, poster: tile.poster, muted: true });
  open.addEventListener("click", () => openViewer(tiles, tiles.indexOf(tile), { pick: pickInViewer }));
  const check = document.createElement("button");
  check.type = "button";
  check.className = "check";
  check.textContent = "✓";
  check.setAttribute("aria-label", `Pick video ${i + 1}`);
  check.addEventListener("click", () => {
    tile.picked = !tile.picked;
    update();
  });
  frame.append(open, check);

  const download = document.createElement("a");
  download.className = "button small-button";
  download.href = `${tile.file}?download=1`;
  download.download = "";
  download.textContent = "Download";

  item.append(frame, download);
  tile.el = item;
  return item;
}

function pickAll(on) {
  tiles.forEach((t) => (t.picked = on));
  update();
}

// Redraw the picked marks, the count and the buttons' wording.
function update() {
  if (!saveButton) return;
  const picked = tiles.filter((t) => t.picked);
  const name = character.value.trim();

  for (const t of tiles) {
    t.el.classList.toggle("picked", t.picked);
    t.el.querySelector(".check").setAttribute("aria-pressed", t.picked);
    t.el.querySelector(".saved-tag").textContent = t.savedTo ? `Saved to ${t.savedTo}` : "";
  }
  countLine.textContent = `${picked.length} of ${tiles.length} picked`;

  const unsaved = picked.filter((t) => t.savedTo !== name);
  if (saving) saveButton.textContent = "Saving…";
  else if (!picked.length) saveButton.textContent = "Tick videos to pick them";
  else if (!name) saveButton.textContent = "Type a name to save";
  else if (!unsaved.length) saveButton.textContent = `Saved to ${name} ✓`;
  else saveButton.textContent = `Save ${unsaved.length} to ${name}`;
  saveButton.disabled = saving || !name || !unsaved.length;

  bulkButton.textContent = picked.length ? `Download ${picked.length} (zip)` : "Download selected";
  bulkButton.disabled = !picked.length;
}

async function savePicked() {
  const name = character.value.trim();
  const todo = tiles.filter((t) => t.picked && t.savedTo !== name);
  saving = true;
  update();
  try {
    for (const t of todo) {
      const res = await fetch(`api/videos/${t.id}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ character: name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      t.savedTo = name;
    }
  } catch (err) {
    characterError.textContent = err.message || "Couldn't save. Is the server running?";
    characterError.hidden = false;
  } finally {
    saving = false;
    update();
  }
}

function downloadPicked() {
  const ids = tiles.filter((t) => t.picked).map((t) => t.id);
  if (!ids.length) return;
  const link = document.createElement("a");
  const name = encodeURIComponent(character.value.trim());
  link.href = `api/videos-zip?ids=${ids.join(",")}${name ? `&name=${name}` : ""}`;
  link.download = "";
  link.click();
}

character.addEventListener("input", update);
