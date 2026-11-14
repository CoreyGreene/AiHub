// The Library tab: every saved character, shown with its first picture.
// Tap one to open it (#library/<folder>) and see all of its pictures,
// either as small pictures (two across, no words) or full with details.

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
  layout = localStorage.getItem(LAYOUT_KEY) === "thumbs" ? "thumbs" : "full";
} catch {}

layoutButtons.addEventListener("click", (event) => {
  const button = event.target.closest("[data-layout]");
  if (!button) return;
  layout = button.dataset.layout;
  try {
    localStorage.setItem(LAYOUT_KEY, layout);
  } catch {}
  showLayout();
});

function showLayout() {
  list.classList.toggle("thumbs", layout === "thumbs");
  for (const b of layoutButtons.querySelectorAll("[data-layout]")) {
    b.setAttribute("aria-pressed", b.dataset.layout === layout);
  }
}

const pictures = (n) => `${n} picture${n === 1 ? "" : "s"}`;

export function loadLibrary(folder) {
  window.scrollTo(0, 0);
  if (folder) showCharacter(decodeURIComponent(folder));
  else showAll();
}

async function showAll() {
  title.textContent = "Library";
  back.hidden = count.hidden = layoutButtons.hidden = true;
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

async function showCharacter(folder) {
  back.hidden = layoutButtons.hidden = false;
  title.textContent = "…";
  count.hidden = true;
  list.className = "character-pictures";
  showLayout();
  list.innerHTML = `<p class="muted">Loading…</p>`;
  try {
    const res = await fetch(`api/characters/${encodeURIComponent(folder)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    title.textContent = data.name;
    count.textContent = `${pictures(data.pictures.length)}. To add more, make a picture with the name ${data.name} and press Save.`;
    count.hidden = false;
    shown = data.pictures;
    list.replaceChildren(...data.pictures.map(pictureCard));
  } catch (err) {
    title.textContent = "Library";
    list.innerHTML = `<p class="muted"></p>`;
    list.firstChild.textContent = err.message || "Couldn't load this character. Is the server running?";
  }
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
