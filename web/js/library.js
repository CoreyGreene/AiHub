// The Library tab: every saved character, shown with its first picture.
// Tap one to open it (#library/<folder>) and see all of its pictures,
// either as small pictures (two across, no words), full with details, or
// by date: one card per day, tap it (#library/<folder>/<date>) for that
// day's pictures.

const list = document.getElementById("library-list");
const title = document.getElementById("library-title");
const count = document.getElementById("library-count");
const back = document.getElementById("library-back");
const layoutButtons = document.getElementById("library-layout");
const viewer = document.getElementById("picture-viewer");
const viewerImage = document.getElementById("viewer-image");

// Tapping a picture shows it on its own, centred on a dark screen. Swipe
// left or right (or use the arrows) to go through the character's pictures.
let shown = []; // the character's pictures
let at = 0; // which one the viewer shows

function openViewer(index) {
  at = index;
  showInViewer();
  viewer.showModal();
}

function showInViewer() {
  viewerImage.src = shown[at].image;
  document.getElementById("viewer-count").textContent = `${at + 1} of ${shown.length}`;
  document.getElementById("viewer-prev").disabled = at === 0;
  document.getElementById("viewer-next").disabled = at === shown.length - 1;
}

function step(by) {
  const next = at + by;
  if (next < 0 || next >= shown.length) return;
  at = next;
  showInViewer();
}

document.getElementById("viewer-prev").addEventListener("click", () => step(-1));
document.getElementById("viewer-next").addEventListener("click", () => step(1));
document.getElementById("viewer-close").addEventListener("click", () => viewer.close());
viewer.addEventListener("click", (event) => {
  if (event.target === viewer || event.target === viewerImage) viewer.close();
});
viewer.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") step(-1);
  if (event.key === "ArrowRight") step(1);
});

// A swipe: mostly sideways and at least 40px. Swipe left = next picture.
let touchStart = null;
viewer.addEventListener("touchstart", (event) => {
  const t = event.changedTouches[0];
  touchStart = { x: t.clientX, y: t.clientY };
}, { passive: true });
viewer.addEventListener("touchend", (event) => {
  if (!touchStart) return;
  const t = event.changedTouches[0];
  const dx = t.clientX - touchStart.x;
  const dy = t.clientY - touchStart.y;
  touchStart = null;
  if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) step(dx < 0 ? 1 : -1);
});

// The chosen layout is remembered on this phone (if the browser allows).
const LAYOUT_KEY = "imageai.libraryLayout";
let layout = "full";
try {
  const saved = localStorage.getItem(LAYOUT_KEY);
  if (["thumbs", "dates"].includes(saved)) layout = saved;
} catch {}

let folderShown = ""; // the character on screen
let dateShown = ""; // the day on screen, or "" for all of them

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
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    title.textContent = data.name;
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
      <a class="button small-button" download>Download</a>
    </div>`;
  const link = item.querySelector(".saved-image");
  link.href = pic.image;
  link.addEventListener("click", (event) => {
    event.preventDefault();
    openViewer(index);
  });
  item.querySelector("img").src = pic.image;
  item.querySelector(".saved-prompt").textContent = pic.prompt;
  const made = pic.made ? new Date(pic.made).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
  item.querySelector(".saved-meta").textContent = [pic.theme, made].filter(Boolean).join(" · ");
  item.querySelector("[download]").href = `${pic.image}?download=1`;
  return item;
}
