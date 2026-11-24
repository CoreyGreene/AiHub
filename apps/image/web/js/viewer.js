// One picture at a time, big, centred on a dark screen: used by the
// Library and by Create's results. Swipe left or right (or use the arrows
// and arrow keys) to go through the list. Pinch to zoom the picture, drag
// to move around it, tap to zoom back out. With `pick`, a Pick button shows
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
  resetZoom();
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
  if (event.target === image && scale > 1) resetZoom(); // tap a zoomed picture: back to normal
  else if (event.target === viewer || event.target === image) viewer.close();
});
viewer.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") step(-1);
  if (event.key === "ArrowRight") step(1);
});

// Pinch to zoom (two fingers), drag to move a zoomed picture (one finger).
// Only the picture's look on screen changes; the file is untouched.
let scale = 1;
let x = 0;
let y = 0;
let pinch = null; // { dist, scale } when two fingers went down
let drag = null; // last finger spot, while moving a zoomed picture
let zoomTouch = false; // this touch zoomed or moved: it isn't a swipe
const MAX_ZOOM = 5;

const distance = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

function applyZoom() {
  // Keep the picture covering its box: no dragging it off screen.
  const maxX = ((scale - 1) * image.clientWidth) / 2;
  const maxY = ((scale - 1) * image.clientHeight) / 2;
  x = clamp(x, -maxX, maxX);
  y = clamp(y, -maxY, maxY);
  image.style.transform = scale > 1 ? `translate(${x}px, ${y}px) scale(${scale})` : "";
}

function resetZoom() {
  scale = 1;
  x = y = 0;
  applyZoom();
}

image.addEventListener("touchstart", (event) => {
  if (event.touches.length === 2) {
    pinch = { dist: distance(event.touches), scale };
    drag = null;
    zoomTouch = true;
  } else if (event.touches.length === 1 && scale > 1) {
    drag = { x: event.touches[0].clientX, y: event.touches[0].clientY };
  }
}, { passive: true });
image.addEventListener("touchmove", (event) => {
  if (pinch && event.touches.length === 2) {
    event.preventDefault();
    scale = clamp((pinch.scale * distance(event.touches)) / pinch.dist, 1, MAX_ZOOM);
    applyZoom();
  } else if (drag && event.touches.length === 1) {
    event.preventDefault();
    const t = event.touches[0];
    x += t.clientX - drag.x;
    y += t.clientY - drag.y;
    drag = { x: t.clientX, y: t.clientY };
    applyZoom();
  }
}, { passive: false });
image.addEventListener("touchend", (event) => {
  if (event.touches.length < 2) pinch = null;
  if (!event.touches.length) drag = null;
});

// A swipe: mostly sideways and at least 40px. Swipe left = next picture.
// Not while zoomed in (then one finger moves the picture).
let touchStart = null;
viewer.addEventListener("touchstart", (event) => {
  if (event.touches.length === 1) zoomTouch = scale > 1;
  const t = event.changedTouches[0];
  touchStart = { x: t.clientX, y: t.clientY };
}, { passive: true });
viewer.addEventListener("touchend", (event) => {
  if (!touchStart || event.touches.length) return;
  if (zoomTouch) {
    touchStart = null;
    return;
  }
  const t = event.changedTouches[0];
  const dx = t.clientX - touchStart.x;
  const dy = t.clientY - touchStart.y;
  touchStart = null;
  if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) step(dx < 0 ? 1 : -1);
});
