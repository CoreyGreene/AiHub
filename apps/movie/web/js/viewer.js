// One video at a time, big and playing, centred on a dark screen: used by the
// Library and by Create's results. Swipe left or right (or use the arrows
// and arrow keys) to go through the list. With `pick`, a Pick button shows
// too, so you can choose videos while looking at them full size.

const viewer = document.getElementById("video-viewer");
const player = document.getElementById("viewer-video");
const countLine = document.getElementById("viewer-count");
const prev = document.getElementById("viewer-prev");
const next = document.getElementById("viewer-next");
const pickButton = document.getElementById("viewer-pick");

let items = []; // [{ file, poster }]: the same array the caller keeps, so new videos show up
let at = 0;
let pick = null; // { isPicked(i), toggle(i) } or null

// items: [{ file, poster }]. pick (optional): { isPicked(i), toggle(i) }.
export function openViewer(list, index, options = {}) {
  items = list;
  at = index;
  pick = options.pick || null;
  show();
  if (!viewer.open) viewer.showModal();
}

// Call when the list grows while the viewer is open (videos still coming).
export function refreshViewer() {
  if (viewer.open) show();
}

function show() {
  if (player.getAttribute("src") !== items[at].file) {
    player.poster = items[at].poster;
    player.src = items[at].file;
    player.play().catch(() => {}); // a phone may want a tap on Play first
  }
  countLine.textContent = `${at + 1} of ${items.length}`;
  prev.disabled = at === 0;
  next.disabled = at === items.length - 1;
  pickButton.hidden = !pick;
  if (pick) {
    const on = pick.isPicked(at);
    pickButton.textContent = on ? "Picked ✓" : "Pick this one";
    pickButton.setAttribute("aria-pressed", on);
  }
}

function step(by) {
  const to = at + by;
  if (to < 0 || to >= items.length) return;
  at = to;
  show();
}

prev.addEventListener("click", () => step(-1));
next.addEventListener("click", () => step(1));
pickButton.addEventListener("click", () => {
  pick?.toggle(at);
  show();
});
document.getElementById("viewer-close").addEventListener("click", () => viewer.close());
// Tapping the dark area closes it (tapping the video is for its controls).
viewer.addEventListener("click", (event) => {
  if (event.target === viewer) viewer.close();
});
viewer.addEventListener("close", () => {
  player.pause();
  player.removeAttribute("src");
  player.load(); // stops it downloading
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
