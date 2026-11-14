// Advanced results: a grid of pictures. Tap pictures to pick them, then
// save the picked ones to a character. Each picture has its own Download;
// on a computer there's also "Download selected" (one zip file). Phones
// don't get the bulk option: one download per picture.

const character = document.getElementById("character");
const characterError = document.getElementById("character-error");

let tiles = []; // { id, url, picked, savedTo, el }
let saveButton = null;
let bulkButton = null;
let countLine = null;
let saving = false;

export function showGrid(result, pictures, blocked, onReset) {
  tiles = pictures.map((p) => ({ id: p.picture, url: p.image, picked: false, savedTo: null }));

  const box = document.createElement("div");
  box.className = "picks";

  if (blocked) {
    const note = document.createElement("p");
    note.className = "note small";
    note.textContent = `${blocked} picture${blocked > 1 ? "s" : ""} didn't pass the safety check and ${blocked > 1 ? "were" : "was"} left out.`;
    box.append(note);
  }

  // Picked count with Select all / none.
  const bar = document.createElement("div");
  bar.className = "pick-bar";
  countLine = document.createElement("span");
  countLine.className = "muted";
  const all = textButton("Select all", () => pickAll(true));
  const none = textButton("None", () => pickAll(false));
  bar.append(countLine, all, none);

  const grid = document.createElement("div");
  grid.className = "pick-grid";
  grid.append(...tiles.map(tileFor));

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
    saveButton = bulkButton = null;
    onReset();
  });

  const actions = document.createElement("div");
  actions.className = "actions";
  actions.append(bulkButton, reset);

  box.append(bar, grid, saveButton, actions);
  result.replaceChildren(box);
  update();
}

function textButton(text, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "link-button";
  b.textContent = text;
  b.addEventListener("click", onClick);
  return b;
}

function tileFor(tile, i) {
  const item = document.createElement("div");
  item.className = "pick";

  // The picture itself is the on/off button for picking it.
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "pick-toggle";
  toggle.setAttribute("aria-label", `Picture ${i + 1}`);
  toggle.innerHTML = `<img alt=""><span class="check" aria-hidden="true">✓</span><span class="saved-tag"></span>`;
  toggle.querySelector("img").src = tile.url;
  toggle.addEventListener("click", () => {
    tile.picked = !tile.picked;
    update();
  });

  const download = document.createElement("a");
  download.className = "button small-button";
  download.href = `${tile.url}?download=1`;
  download.download = "";
  download.textContent = "Download";

  item.append(toggle, download);
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
    t.el.querySelector(".pick-toggle").setAttribute("aria-pressed", t.picked);
    t.el.querySelector(".saved-tag").textContent = t.savedTo ? `Saved to ${t.savedTo}` : "";
  }
  countLine.textContent = `${picked.length} of ${tiles.length} picked`;

  const unsaved = picked.filter((t) => t.savedTo !== name);
  if (saving) saveButton.textContent = "Saving…";
  else if (!picked.length) saveButton.textContent = "Tap pictures to pick them";
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
      const res = await fetch(`api/pictures/${t.id}/save`, {
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
  link.href = `api/pictures-zip?ids=${ids.join(",")}${name ? `&name=${name}` : ""}`;
  link.download = "";
  link.click();
}

character.addEventListener("input", update);
