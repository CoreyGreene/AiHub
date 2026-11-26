// The model page's Compare (wide screens): a reference model (settings: references, e.g. the game's Becky) beside
// this one. Both are scaled to the same height and seen by the same camera, framed from 10% to 90% of the view, so
// the lines across them (app.css: .compare-lines) mark tenths of their height. Turning one turns the other.

import { api } from "./api.js";

const toggle = document.getElementById("compare-toggle");
const pick = document.getElementById("compare-with");
const note = document.getElementById("compare-note");
const box = document.getElementById("compare-box");
const single = document.getElementById("viewer-box");
const left = document.getElementById("compare-left");
const right = document.getElementById("compare-right");
const FOV = 12; // degrees: narrow, so near and far parts of a figure aren't stretched apart
const SHOWN = 1.25; // the view shows 1.25 figure-heights: the figure fills 80% of it, 10% above and below
const DISTANCE = SHOWN / 2 / Math.tan((FOV / 2) * (Math.PI / 180));

let references = [];
let current = { name: "", url: "" }; // the model on the page
let on = false;

for (const v of [left, right]) {
  v.fieldOfView = `${FOV}deg`;
  v.setAttribute("min-field-of-view", "5deg");
  v.setAttribute("max-field-of-view", "45deg");
  v.setAttribute("min-camera-orbit", "auto auto 0.5m");
  v.setAttribute("max-camera-orbit", "auto auto 30m");
  v.addEventListener("load", () => fit(v));
  // turning (or zooming) one turns the other the same way
  v.addEventListener("camera-change", (e) => {
    if (e.detail.source !== "user-interaction") return;
    const other = v === left ? right : left;
    const o = v.getCameraOrbit();
    other.cameraOrbit = `${o.theta}rad ${o.phi}rad ${o.radius}m`;
  });
}

// Scale the figure to a height of 1 and point the camera at its middle, from the same distance on both sides.
function fit(v) {
  const size = v.getDimensions();
  const middle = v.getBoundingBoxCenter();
  if (!size.y) return;
  const s = 1 / size.y;
  v.scale = `${s} ${s} ${s}`;
  v.cameraTarget = `${middle.x * s}m ${middle.y * s}m ${middle.z * s}m`;
  v.cameraOrbit = `0deg 90deg ${DISTANCE}m`;
  v.jumpCameraToGoal();
}

async function loadReferences() {
  if (references.length) return;
  try {
    references = await api("api/references");
  } catch {
    references = [];
  }
  pick.replaceChildren(...references.map((r) => new Option(r.name, r.url)));
}

function draw() {
  toggle.setAttribute("aria-pressed", String(on));
  toggle.textContent = on ? "Stop comparing" : "Compare";
  pick.hidden = note.hidden = !on || !references.length;
  box.hidden = !on;
  single.hidden = on;
  if (!on) return;
  if (!references.length) {
    note.hidden = false;
    note.textContent = "Nothing to compare with yet: add a model to references in 3D AI's settings.local.json.";
    return;
  }
  const ref = references.find((r) => r.url === pick.value) || references[0];
  if (left.getAttribute("src") !== ref.url) left.setAttribute("src", ref.url);
  document.getElementById("compare-left-name").textContent = ref.name;
  document.getElementById("compare-right-name").textContent = current.name;
  if (current.url && right.getAttribute("src") !== current.url) right.setAttribute("src", current.url);
  if (!current.url) right.removeAttribute("src");
}

toggle.addEventListener("click", async () => {
  on = !on;
  if (on) await loadReferences();
  draw();
});
pick.addEventListener("change", draw);

// library.js: the model (version) shown on the page changed.
export function compareWith(name, url) {
  current = { name, url: url || "" };
  if (on) draw();
}

// library.js: leaving the model page.
export function stopComparing() {
  on = false;
  draw();
}
