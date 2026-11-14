// One picture at a time, big, centred on a dark screen: used by the
// Library and by Create's results. Swipe left or right (or use the arrows
// and arrow keys) to go through the list. With `pick`, a Pick button shows
// too, so you can choose pictures while looking at them full size.

const viewer = document.getElementById("picture-viewer");
const image = document.getElementById("viewer-image");
const countLine = document.getElementById("viewer-count");
const prev = document.getElementById("viewer-prev");
const next = document.getElementById("viewer-next");
const pickButton = document.getElementById("viewer-pick");

let items = []; // [{ image }]: the same array the caller keeps, so new pictures show up
let at = 0;
let pick = null; // { isPicked(i), toggle(i) } or null

// items: [{ image: url }]. pick (optional): { isPicked(i), toggle(i) }.
export function openViewer(list, index, options = {}) {
  items = list;
  at = index;
  pick = options.pick || null;
  show();
  if (!viewer.open) viewer.showModal();
}

// Call when the list grows while the viewer is open (pictures still coming).
export function refreshViewer() {
  if (viewer.open) show();
}

function show() {
  image.src = items[at].image;
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
viewer.addEventListener("click", (event) => {
  if (event.target === viewer || event.target === image) viewer.close();
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
