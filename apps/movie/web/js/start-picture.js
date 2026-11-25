// Create → Start picture: themes that can (LTX) begin the video from a
// picture, and Custom when its model can. It's sent to the server as soon
// as it's chosen; Generate sends its id. Shown only where it can be used.

import { chosenTheme, whenThemeChanges } from "./theme-picker.js";

const els = {
  field: document.getElementById("start-field"),
  image: document.getElementById("start-image"),
  file: document.getElementById("start-file"),
  choose: document.getElementById("start-choose"),
  rotate: document.getElementById("start-rotate"),
  remove: document.getElementById("start-remove"),
  error: document.getElementById("start-error"),
  view: document.getElementById("view-create"),
};

let picture = null; // { id, image } once the server has it
let customTakesPicture = false; // the Custom tab's model can use one (from the server)

fetch("api/settings")
  .then((res) => res.json())
  .then((data) => {
    customTakesPicture = Boolean(data.custom_start_picture);
    showStartField();
  })
  .catch(() => {});

// The id to send with Generate, or "" (none, or this theme can't use one).
export function startPictureId() {
  return picture && usable() ? picture.id : "";
}

function usable() {
  if (els.view.dataset.mode === "custom") return customTakesPicture;
  return Boolean(chosenTheme()?.start_picture);
}

export function showStartField() {
  els.field.hidden = !usable();
}

function show() {
  els.image.hidden = !picture;
  if (picture) els.image.src = picture.image;
  els.remove.hidden = els.rotate.hidden = !picture;
  els.choose.textContent = picture ? "Change" : "Choose a picture";
}

els.file.addEventListener("change", async () => {
  const file = els.file.files[0];
  els.file.value = ""; // the same file can be picked again
  if (!file) return;
  els.error.hidden = true;
  els.choose.textContent = "Sending…";
  try {
    const res = await fetch("api/start-pictures", { method: "POST", body: file });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    picture = data;
  } catch (err) {
    els.error.textContent = err.message || "Couldn't send the picture. Is the server running?";
    els.error.hidden = false;
  }
  show();
});

// A quarter turn clockwise; the server keeps it as a new picture.
els.rotate.addEventListener("click", async () => {
  els.rotate.disabled = true;
  els.error.hidden = true;
  try {
    const res = await fetch(`api/start-pictures/${picture.id}/rotate`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    picture = data;
  } catch (err) {
    els.error.textContent = err.message || "Couldn't turn the picture. Is the server running?";
    els.error.hidden = false;
  } finally {
    els.rotate.disabled = false;
  }
  show();
});

els.remove.addEventListener("click", () => {
  picture = null;
  show();
});

whenThemeChanges(showStartField);
