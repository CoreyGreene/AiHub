// The Library tab: every saved character, shown with its first picture.
// Tap one to open it (#library/<folder>) and see all of its pictures,
// either as small pictures (two across, no words), full with details, or
// by date: one card per day, tap it (#library/<folder>/<date>) for that
// day's pictures. The tick button turns on choosing: tap pictures to pick
// them, then download them as one zip or delete them.

import { startFrom } from "./create.js";
import { openViewer } from "./viewer.js";

const list = document.getElementById("library-list");
const title = document.getElementById("library-title");
const count = document.getElementById("library-count");
const back = document.getElementById("library-back");
const layoutButtons = document.getElementById("library-layout");

// Tapping a picture shows it big (viewer.js); swipe through the ones shown.
let shown = []; // the pictures on screen

// The chosen layout is remembered on this phone (if the browser allows).
const LAYOUT_KEY = "imageai.libraryLayout";
let layout = "full";
try {
  const saved = localStorage.getItem(LAYOUT_KEY);
  if (["thumbs", "dates"].includes(saved)) layout = saved;
} catch {}

let folderShown = ""; // the character on screen
let dateShown = ""; // the day on screen, or "" for all of them
let nameShown = ""; // that character's name, for the zip file

// Choosing pictures (the tick button).
const selectToggle = document.getElementById("select-toggle");
const selectBar = document.getElementById("select-bar");
const selectCount = document.getElementById("select-count");
const selectAll = document.getElementById("select-all");
const selectZip = document.getElementById("select-zip");
const selectDelete = document.getElementById("select-delete");
const selectActions = document.getElementById("select-actions");
const deleteAsk = document.getElementById("delete-ask");
const deleteQuestion = document.getElementById("delete-question");
const selectError = document.getElementById("select-error");
let selecting = false;
const chosen = new Set(); // picture ids

function setSelecting(on) {
  selecting = on;
  chosen.clear();
  selectToggle.setAttribute("aria-pressed", on);
  list.classList.toggle("selecting", on);
  for (const card of list.querySelectorAll(".saved-picture.chosen")) card.classList.remove("chosen");
  selectBar.hidden = !on;
  showChosen();
}

function showChosen() {
  const n = chosen.size;
  selectCount.textContent = n ? `${pictures(n)} chosen` : "Tap pictures to choose them";
  selectAll.textContent = n && n === shown.length ? "None" : "All";
  selectZip.disabled = selectDelete.disabled = !n;
  deleteAsk.hidden = true;
  selectActions.hidden = false;
  selectError.hidden = true;
}

function toggleChosen(pic, card) {
  if (chosen.has(pic.id)) chosen.delete(pic.id);
  else chosen.add(pic.id);
  card.classList.toggle("chosen", chosen.has(pic.id));
  card.querySelector(".saved-image").setAttribute("aria-pressed", chosen.has(pic.id));
  showChosen();
}

selectToggle.addEventListener("click", () => setSelecting(!selecting));

selectAll.addEventListener("click", () => {
  const all = chosen.size !== shown.length;
  chosen.clear();
  if (all) shown.forEach((pic) => chosen.add(pic.id));
  for (const card of list.querySelectorAll(".saved-picture")) {
    card.classList.toggle("chosen", all);
    card.querySelector(".saved-image").setAttribute("aria-pressed", all);
  }
  showChosen();
});

selectZip.addEventListener("click", () => {
  const link = document.createElement("a");
  link.href = `api/pictures-zip?ids=${[...chosen].join(",")}&name=${encodeURIComponent(nameShown)}`;
  link.download = "";
  document.body.append(link);
  link.click();
  link.remove();
});

// Delete asks first, in the bar itself.
selectDelete.addEventListener("click", () => {
  deleteQuestion.textContent = `Delete ${pictures(chosen.size)} for good?`;
  selectActions.hidden = true;
  deleteAsk.hidden = false;
});
document.getElementById("delete-no").addEventListener("click", showChosen);
document.getElementById("delete-yes").addEventListener("click", async () => {
  const ids = [...chosen];
  try {
    const res = await fetch("api/pictures-delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    if (!res.ok) throw new Error();
  } catch {
    showChosen();
    selectError.textContent = "Couldn't delete. Is the server running?";
    selectError.hidden = false;
    return;
  }
  // Nothing left of this day or character: go up a level.
  const left = shown.length - ids.length;
  if (left <= 0 && dateShown) location.hash = `#library/${encodeURIComponent(folderShown)}`;
  else if (left <= 0 && shown.length) location.hash = "#library";
  else showCharacter(folderShown, dateShown);
});

layoutButtons.addEventListener("click", (event) => {
  const button = event.target.closest("[data-layout]");
  if (!button) return;
  layout = button.dataset.layout;
  try {
    localStorage.setItem(LAYOUT_KEY, layout);
  } catch {}
  // Inside one day, any choice goes back to the whole character.
  if (dateShown) location.hash = `#library/${encodeURIComponent(folderShown)}`;
  else showCharacter(folderShown);
});

function showLayout() {
  for (const b of layoutButtons.querySelectorAll("[data-layout]")) {
    b.setAttribute("aria-pressed", b.dataset.layout === layout);
  }
}

const pictures = (n) => `${n} picture${n === 1 ? "" : "s"}`;

// The day a picture was made, on this phone's clock: "2026-11-14".
function dayOf(pic) {
  const d = new Date(pic.made);
  if (isNaN(d)) return "unknown";
  const two = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}`;
}

function dayName(day) {
  if (day === "unknown") return "Unknown date";
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function loadLibrary(folder, date) {
  window.scrollTo(0, 0);
  if (folder) showCharacter(decodeURIComponent(folder), date || "");
  else showAll();
}

async function showAll() {
  setSelecting(false);
  title.textContent = "Library";
  back.hidden = count.hidden = layoutButtons.hidden = true;
  back.href = "#library";
  back.textContent = "← All characters";
  list.className = "library-grid";
  try {
    const res = await fetch("api/characters");
    const characters = await res.json();
    if (!characters.length) {
      list.innerHTML = `<p class="muted">No characters yet. Make a picture, type a name and press Save.</p>`;
      return;
    }
    list.replaceChildren(...characters.map(card));
  } catch {
    list.innerHTML = `<p class="muted">Couldn't load the library. Is the server running?</p>`;
  }
}

function card(character) {
  const item = document.createElement("a");
  item.className = "character";
  item.href = `#library/${encodeURIComponent(character.folder)}`;
  item.innerHTML = `<img alt="" loading="lazy"><h3></h3><p class="muted"></p>`;
  item.querySelector("img").src = character.cover;
  item.querySelector("h3").textContent = character.name;
  item.querySelector("p").textContent = pictures(character.count);
  return item;
}

async function showCharacter(folder, date = "") {
  folderShown = folder;
  dateShown = date;
  setSelecting(false);
  // Choosing works where pictures are shown, not on the list of days.
  selectToggle.hidden = layout === "dates" && !date;
  back.hidden = layoutButtons.hidden = false;
  back.href = date ? `#library/${encodeURIComponent(folder)}` : "#library";
  back.textContent = date ? "← All dates" : "← All characters";
  title.textContent = "…";
  count.hidden = true;
  showLayout();
  list.className = "character-pictures";
  list.innerHTML = `<p class="muted">Loading…</p>`;
  try {
    const res = await fetch(`api/characters/${encodeURIComponent(folder)}`);
    if (res.status === 404) {
      location.hash = "#library"; // gone (its last pictures were deleted)
      return;
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    title.textContent = nameShown = data.name;
    count.hidden = false;
    if (date) {
      // One day: small pictures, the viewer goes through that day only.
      shown = data.pictures.filter((pic) => dayOf(pic) === date);
      count.textContent = `${pictures(shown.length)} on ${dayName(date)}.`;
      list.className = "character-pictures thumbs";
      list.replaceChildren(...shown.map(pictureCard));
    } else if (layout === "dates") {
      list.className = "library-grid days";
      const days = byDay(data.pictures);
      count.textContent = `${pictures(data.pictures.length)} on ${days.length} day${days.length === 1 ? "" : "s"}. Tap a day to see its pictures.`;
      list.replaceChildren(...days.map((day) => dayCard(folder, day)));
    } else {
      shown = data.pictures;
      count.textContent = `${pictures(data.pictures.length)}. To add more, make a picture with the name ${data.name} and press Save.`;
      list.classList.toggle("thumbs", layout === "thumbs");
      list.replaceChildren(...data.pictures.map(pictureCard));
    }
  } catch (err) {
    title.textContent = "Library";
    list.innerHTML = `<p class="muted"></p>`;
    list.firstChild.textContent = err.message || "Couldn't load this character. Is the server running?";
  }
}

// The pictures grouped by day, newest day first.
function byDay(pics) {
  const days = new Map();
  for (const pic of pics) {
    const day = dayOf(pic);
    if (!days.has(day)) days.set(day, []);
    days.get(day).push(pic);
  }
  return [...days].map(([day, list]) => ({ day, pics: list })).sort((a, b) => (a.day < b.day ? 1 : -1));
}

function dayCard(folder, { day, pics }) {
  const item = document.createElement("a");
  item.className = "character";
  item.href = `#library/${encodeURIComponent(folder)}/${day}`;
  item.innerHTML = `<img alt="" loading="lazy"><h3></h3><p class="muted"></p>`;
  item.querySelector("img").src = pics[0].image;
  item.querySelector("h3").textContent = dayName(day);
  item.querySelector("p").textContent = pictures(pics.length);
  return item;
}

function pictureCard(pic, index) {
  const item = document.createElement("article");
  item.className = "saved-picture";
  item.innerHTML = `
    <a class="saved-image"><img alt="" loading="lazy"></a>
    <div class="saved-info">
      <p class="saved-prompt"></p>
      <p class="muted small saved-meta"></p>
      <button type="button" class="button small-button saved-copy">Copy settings</button>
      <a class="button small-button" download>Download</a>
    </div>`;
  const link = item.querySelector(".saved-image");
  link.href = pic.image;
  link.addEventListener("click", (event) => {
    event.preventDefault();
    if (selecting) toggleChosen(pic, item);
    else openViewer(shown, index);
  });
  item.querySelector("img").src = pic.image;
  item.querySelector(".saved-prompt").textContent = pic.prompt;
  const made = pic.made ? new Date(pic.made).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
  item.querySelector(".saved-meta").textContent = [pic.theme, made].filter(Boolean).join(" · ");
  item.querySelector("[download]").href = `${pic.image}?download=1`;
  const copy = item.querySelector(".saved-copy");
  copy.addEventListener("click", async () => {
    copy.disabled = true;
    try {
      const res = await fetch(`api/pictures/${pic.id}/recipe`);
      const recipe = await res.json();
      if (!res.ok) throw new Error(recipe.detail);
      startFrom(recipe);
    } catch (err) {
      copy.textContent = err.message ? "Picture not found" : "Couldn't copy. Try again";
    } finally {
      copy.disabled = false;
    }
  });
  return item;
}
