// The Library tab, in two parts. Characters: every saved character, shown
// with its first picture. Tap one to open it (#library/<folder>) and see all
// of its pictures, either as small pictures (two across, no words), full
// with details, or by date: one card per day, tap it (#library/<folder>/<date>)
// for that day's pictures. Staging (#library/_staging): the pictures
// workflows made, by group; open one (#library/_staging/<folder>), choose the
// good ones and add them to a character. ("_" is never in a folder name.)
// The tick button turns on choosing: tap pictures to pick them, then
// download them as one zip or delete them (or, in staging, keep them).

import { editFrom, startFrom } from "./create.js";
import { openViewer } from "./viewer.js";
import { pickCharacter } from "./character-picker.js";

const STAGING = "_staging";
const ITEMS = "_items";
let place = "characters"; // or "items" (characters whose name starts with "Item") or "staging"
const api = () => (place === "staging" ? "api/staging" : "api/characters");
const listHash = () => (place === "staging" ? `#library/${STAGING}` : place === "items" ? `#library/${ITEMS}` : "#library");
const groupHash = (folder) => `${listHash()}/${encodeURIComponent(folder)}`;

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

// The list of characters (or items: the Items tab) with a search box. An item
// is any character whose name starts with the word "Item" ("Item Fridge").
const filterBar = document.getElementById("library-filter");
const search = document.getElementById("library-search");
let everyone = []; // every character from the server, before the filter
const isItem = (name) => /^items?\b/i.test(name.trim());

let folderShown = ""; // the character on screen
let dateShown = ""; // the day on screen, or "" for all of them
let nameShown = ""; // that character's name, for the zip file

// Pictures come a page at a time (settings.json: page_size for full
// pictures, thumbs_page_size for small ones; 0 = all at once).
const pageSizes = fetch("api/settings")
  .then((res) => res.json())
  .then((data) => ({ full: data.page_size || 0, thumbs: data.thumbs_page_size || 0 }))
  .catch(() => ({ full: 0, thumbs: 0 }));
let pageShown = 0; // which page, from 0
let pageFor = ""; // the folder and layout that page belongs to

// Choosing pictures (the tick button).
const selectToggle = document.getElementById("select-toggle");
const selectBar = document.getElementById("select-bar");
const selectCount = document.getElementById("select-count");
const selectAll = document.getElementById("select-all");
const selectZip = document.getElementById("select-zip");
const selectDelete = document.getElementById("select-delete");
const selectApprove = document.getElementById("select-approve");
const approveBox = document.getElementById("approve-box");
const approveName = document.getElementById("approve-name");
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
  selectZip.disabled = selectDelete.disabled = selectApprove.disabled = !n;
  selectApprove.hidden = place !== "staging";
  deleteAsk.hidden = approveBox.hidden = true;
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
  afterMoving(ids.length);
});

// Nothing left of this day or character (or staging group): go up a level.
function afterMoving(gone, message = "") {
  const left = shown.length - gone;
  if (left <= 0 && dateShown) location.hash = groupHash(folderShown);
  else if (left <= 0 && shown.length) location.hash = listHash();
  else showCharacter(folderShown, dateShown, message);
}

// Staging: add the chosen pictures to a character (they leave staging).
selectApprove.addEventListener("click", () => {
  selectActions.hidden = true;
  approveBox.hidden = false;
  approveName.focus();
});
document.getElementById("approve-no").addEventListener("click", showChosen);
document.getElementById("approve-pick").addEventListener("click", () => pickCharacter(approveName));
document.getElementById("approve-yes").addEventListener("click", async () => {
  const character = approveName.value.trim();
  selectError.hidden = Boolean(character);
  selectError.textContent = "Type a character name, or Pick one.";
  if (!character) return;
  const ids = [...chosen];
  try {
    const res = await fetch("api/staging/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, character }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    afterMoving(ids.length, `Added ${pictures(data.moved)} to ${character}.`);
  } catch (err) {
    selectError.textContent = err.message || "Couldn't add them. Is the server running?";
    selectError.hidden = false;
  }
});

layoutButtons.addEventListener("click", (event) => {
  const button = event.target.closest("[data-layout]");
  if (!button) return;
  layout = button.dataset.layout;
  try {
    localStorage.setItem(LAYOUT_KEY, layout);
  } catch {}
  // Inside one day, any choice goes back to the whole character.
  if (dateShown) location.hash = groupHash(folderShown);
  else showCharacter(folderShown);
});

function showLayout() {
  for (const b of layoutButtons.querySelectorAll("[data-layout]")) {
    b.setAttribute("aria-pressed", b.dataset.layout === layoutHere());
    b.hidden = place === "staging" && b.dataset.layout === "dates"; // staging: no dates
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

// Staging has no "by date" view: it shows as full pictures there.
const layoutHere = () => (place === "staging" && layout === "dates" ? "full" : layout);

// #library[/<folder>[/<date>]], #library/_items[/<folder>[/<date>]] or #library/_staging[/<folder>]
export function loadLibrary(first, second, third) {
  window.scrollTo(0, 0);
  const was = place;
  place = first === STAGING ? "staging" : first === ITEMS ? "items" : "characters";
  if (place !== was) search.value = ""; // a search is for the tab it was typed on
  const [folder, date] = place === "characters" ? [first, second] : place === "staging" ? [second, ""] : [second, third];
  for (const tab of document.querySelectorAll("#view-library [data-place]")) {
    if (tab.dataset.place === place) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
  if (folder) showCharacter(decodeURIComponent(folder), date || "");
  else showAll();
}

async function showAll() {
  setSelecting(false);
  pageFor = ""; // opening a character again starts at page 1
  const staging = place === "staging";
  title.textContent = staging ? "Staging" : place === "items" ? "Items" : "Characters";
  back.hidden = layoutButtons.hidden = true;
  filterBar.hidden = staging;
  count.hidden = !staging;
  count.textContent = "Pictures made by workflows. Open a group, choose the ones you like and add them to a character.";
  list.className = "library-grid";
  try {
    const res = await fetch(api());
    const characters = await res.json();
    if (!characters.length) {
      list.innerHTML = staging
        ? `<p class="muted">Nothing here. Start a workflow on the Workflows tab; its pictures show up here.</p>`
        : `<p class="muted">No characters yet. Make a picture, type a name and press Save.</p>`;
      return;
    }
    if (staging) {
      list.replaceChildren(...characters.map(card));
      return;
    }
    everyone = characters;
    showFiltered();
  } catch {
    list.innerHTML = `<p class="muted">Couldn't load the library. Is the server running?</p>`;
  }
}

// The characters (or items) whose name has the search words in it.
function showFiltered() {
  const items = place === "items";
  search.placeholder = items ? "Search items" : "Search characters";
  const words = search.value.trim().toLowerCase();
  const found = everyone.filter((c) => isItem(c.name) === items && c.name.toLowerCase().includes(words));
  if (found.length) {
    list.replaceChildren(...found.map(card));
    return;
  }
  const note = document.createElement("p");
  note.className = "muted";
  if (words) note.textContent = `No ${items ? "items" : "characters"} called “${search.value.trim()}”.`;
  else if (items) note.textContent = "No items yet. Save a picture with a name that starts with Item, like “Item Fridge”.";
  else note.textContent = "No characters yet, only items. Make a picture, type a name and press Save.";
  list.replaceChildren(note);
}

search.addEventListener("input", showFiltered);

function card(character) {
  const item = document.createElement("a");
  item.className = "character";
  item.href = groupHash(character.folder);
  item.innerHTML = `<img alt="" loading="lazy"><h3></h3><p class="muted"></p>`;
  item.querySelector("img").src = character.cover;
  item.querySelector("h3").textContent = character.name;
  item.querySelector("p").textContent = pictures(character.count);
  return item;
}

async function showCharacter(folder, date = "", message = "") {
  folderShown = folder;
  dateShown = date;
  setSelecting(false);
  const layout = layoutHere();
  // Choosing works where pictures are shown, not on the list of days.
  selectToggle.hidden = layout === "dates" && !date;
  back.hidden = layoutButtons.hidden = false;
  filterBar.hidden = true;
  back.href = date ? groupHash(folder) : listHash();
  back.textContent = date
    ? "← All dates"
    : place === "staging" ? "← All of staging" : place === "items" ? "← All items" : "← All characters";
  title.textContent = "…";
  count.hidden = true;
  showLayout();
  list.className = "character-pictures";
  list.innerHTML = `<p class="muted">Loading…</p>`;
  try {
    const res = await fetch(`${api()}/${encodeURIComponent(folder)}`);
    if (res.status === 404) {
      location.hash = listHash(); // gone (its last pictures were deleted or moved)
      return;
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    title.textContent = nameShown = data.name;
    count.hidden = false;
    if (date) {
      // One day: small pictures, the viewer goes through that day's page only.
      const day = data.pictures.filter((pic) => dayOf(pic) === date);
      list.className = "character-pictures thumbs";
      startPage(`${folder}/${date}`, day, (await pageSizes).thumbs, `${pictures(day.length)} on ${dayName(date)}.`);
    } else if (layout === "dates") {
      list.className = "library-grid days";
      const days = byDay(data.pictures);
      count.textContent = `${pictures(data.pictures.length)} on ${days.length} day${days.length === 1 ? "" : "s"}. Tap a day to see its pictures.`;
      list.replaceChildren(...days.map((day) => dayCard(folder, day)));
    } else {
      const about =
        (message ? `${message} ` : "") +
        (place === "staging"
          ? `${pictures(data.pictures.length)} from a workflow. Tap the tick, choose the ones you like, then Add to character.`
          : `${pictures(data.pictures.length)}. To add more, make a picture with the name ${data.name} and press Save.`);
      list.classList.toggle("thumbs", layout === "thumbs");
      startPage(`${folder}/${layout}`, data.pictures, (await pageSizes)[layout], about);
    }
  } catch (err) {
    title.textContent = "Library";
    list.innerHTML = `<p class="muted"></p>`;
    list.firstChild.textContent = err.message || "Couldn't load this character. Is the server running?";
  }
}

// Another character, day or layout starts at page 1; after a delete, stay put.
function startPage(key, all, size, about) {
  key = `${place}/${key}`;
  if (pageFor !== key) pageShown = 0;
  pageFor = key;
  showPage(all, size, about);
}

// One page of pictures (all of them when size is 0), with page buttons.
function showPage(all, size, about) {
  const pages = size ? Math.max(1, Math.ceil(all.length / size)) : 1;
  pageShown = Math.min(pageShown, pages - 1);
  const from = size * pageShown;
  shown = size ? all.slice(from, from + size) : all;
  count.textContent = pages > 1 ? `${about} Showing ${from + 1}–${from + shown.length}.` : about;
  list.replaceChildren(...shown.map(pictureCard));
  if (pages === 1) return;

  const bar = document.createElement("nav");
  bar.className = "pager";
  bar.setAttribute("aria-label", "Pages");
  const go = (to) => {
    pageShown = to;
    if (selecting) {
      chosen.clear(); // choosing is per page
      showChosen();
    }
    showPage(all, size, about);
    list.scrollIntoView();
  };
  const button = (text, to, className = "button") => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = className;
    b.textContent = text;
    b.disabled = to < 0 || to >= pages;
    b.addEventListener("click", () => go(to));
    return b;
  };
  // A button per page: all of them when there are few, otherwise the
  // first, the last and the ones next to this page, with … between (so
  // it fits one line on a phone).
  const numbers = document.createElement("div");
  numbers.className = "pager-numbers";
  let last = -1;
  for (let n = 0; n < pages; n++) {
    if (pages > 7 && n > 0 && n < pages - 1 && Math.abs(n - pageShown) > 1) continue;
    if (n - last > 1) numbers.append(Object.assign(document.createElement("span"), { className: "muted", textContent: "…" }));
    last = n;
    const b = button(String(n + 1), n, "button page-number");
    if (n === pageShown) {
      b.setAttribute("aria-current", "page");
      b.setAttribute("aria-label", `Page ${n + 1}, shown now`);
    } else b.setAttribute("aria-label", `Page ${n + 1}`);
    numbers.append(b);
  }
  const arrows = document.createElement("div");
  arrows.className = "pager-arrows";
  arrows.append(button("← Previous", pageShown - 1), button("Next →", pageShown + 1));
  bar.append(numbers, arrows);
  list.append(bar);
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
  item.href = `${groupHash(folder)}/${day}`;
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
      <button type="button" class="button small-button saved-edit">Edit</button>
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
  // Saved to this character when kept; staging groups aren't characters.
  item.querySelector(".saved-edit").addEventListener("click", () =>
    editFrom({ ...pic, character: place === "staging" ? "" : nameShown }),
  );
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
