// The Library tab: every saved character, shown with its first video.
// Tap one to open it (#library/<folder>) and see all of its videos,
// either as small videos (two across, no words), full with details, or
// by date: one card per day, tap it (#library/<folder>/<date>) for that
// day's videos.

const list = document.getElementById("library-list");
const title = document.getElementById("library-title");
const count = document.getElementById("library-count");
const back = document.getElementById("library-back");
const layoutButtons = document.getElementById("library-layout");
const viewer = document.getElementById("video-viewer");
const viewerVideo = document.getElementById("viewer-video");

// Tapping a video plays it on its own, centred on a dark screen. Swipe
// left or right (or use the arrows) to go through the character's videos.
let shown = []; // the character's videos
let at = 0; // which one the viewer shows

function openViewer(index) {
  at = index;
  showInViewer();
  viewer.showModal();
}

function showInViewer() {
  viewerVideo.poster = shown[at].poster;
  viewerVideo.src = shown[at].file;
  viewerVideo.play().catch(() => {}); // a phone may want a tap on Play first
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
// Tapping the dark area closes it (tapping the video is for its controls).
viewer.addEventListener("click", (event) => {
  if (event.target === viewer) viewer.close();
});
viewer.addEventListener("close", () => {
  viewerVideo.pause();
  viewerVideo.removeAttribute("src");
  viewerVideo.load(); // stops it downloading
});
viewer.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") step(-1);
  if (event.key === "ArrowRight") step(1);
});

// A swipe: mostly sideways and at least 40px. Swipe left = next video.
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
const LAYOUT_KEY = "movieai.libraryLayout";
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

const videos = (n) => `${n} video${n === 1 ? "" : "s"}`;

// The day a video was made, on this phone's clock: "2026-11-14".
function dayOf(vid) {
  const d = new Date(vid.made);
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
      list.innerHTML = `<p class="muted">No characters yet. Make a video, type a name and press Save.</p>`;
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
  item.querySelector("p").textContent = videos(character.count);
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
  list.className = "character-videos";
  list.innerHTML = `<p class="muted">Loading…</p>`;
  try {
    const res = await fetch(`api/characters/${encodeURIComponent(folder)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    title.textContent = data.name;
    count.hidden = false;
    if (date) {
      // One day: small videos, the viewer goes through that day only.
      shown = data.videos.filter((pic) => dayOf(pic) === date);
      count.textContent = `${videos(shown.length)} on ${dayName(date)}.`;
      list.className = "character-videos thumbs";
      list.replaceChildren(...shown.map(videoCard));
    } else if (layout === "dates") {
      list.className = "library-grid days";
      const days = byDay(data.videos);
      count.textContent = `${videos(data.videos.length)} on ${days.length} day${days.length === 1 ? "" : "s"}. Tap a day to see its videos.`;
      list.replaceChildren(...days.map((day) => dayCard(folder, day)));
    } else {
      shown = data.videos;
      count.textContent = `${videos(data.videos.length)}. To add more, make a video with the name ${data.name} and press Save.`;
      list.classList.toggle("thumbs", layout === "thumbs");
      list.replaceChildren(...data.videos.map(videoCard));
    }
  } catch (err) {
    title.textContent = "Library";
    list.innerHTML = `<p class="muted"></p>`;
    list.firstChild.textContent = err.message || "Couldn't load this character. Is the server running?";
  }
}

// The videos grouped by day, newest day first.
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
  item.querySelector("img").src = pics[0].poster;
  item.querySelector("h3").textContent = dayName(day);
  item.querySelector("p").textContent = videos(pics.length);
  return item;
}

function videoCard(pic, index) {
  const item = document.createElement("article");
  item.className = "saved-video";
  item.innerHTML = `
    <a class="saved-image"><img alt="" loading="lazy"><span class="play-mark" aria-hidden="true">▶</span></a>
    <div class="saved-info">
      <p class="saved-prompt"></p>
      <p class="muted small saved-meta"></p>
      <a class="button small-button" download>Download</a>
    </div>`;
  const link = item.querySelector(".saved-image");
  link.href = pic.file;
  link.setAttribute("aria-label", "Play");
  link.addEventListener("click", (event) => {
    event.preventDefault();
    openViewer(index);
  });
  item.querySelector("img").src = pic.poster;
  item.querySelector(".saved-prompt").textContent = pic.prompt;
  const made = pic.made ? new Date(pic.made).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
  const length = pic.seconds ? `${pic.seconds} s` : "";
  item.querySelector(".saved-meta").textContent = [pic.theme, length, made].filter(Boolean).join(" · ");
  item.querySelector("[download]").href = `${pic.file}?download=1`;
  return item;
}
