// Create → Start picture: themes that can (LTX) begin the video from a
// picture. It's sent to the server as soon as it's chosen; Generate sends
// its id. Shown only for those themes.

import { chosenTheme, whenThemeChanges } from "./theme-picker.js";

const els = {
  field: document.getElementById("start-field"),
  image: document.getElementById("start-image"),
  file: document.getElementById("start-file"),
  choose: document.getElementById("start-choose"),
  remove: document.getElementById("start-remove"),
  error: document.getElementById("start-error"),
  view: document.getElementById("view-create"),
};

let picture = null; // { id, image } once the server has it

// The id to send with Generate, or "" (none, or this theme can't use one).
export function startPictureId() {
  return picture && usable() ? picture.id : "";
}

function usable() {
  return els.view.dataset.mode !== "custom" && Boolean(chosenTheme()?.start_picture);
}

export function showStartField() {
  els.field.hidden = !usable();
}

function show() {
  els.image.hidden = !picture;
  if (picture) els.image.src = picture.image;
  els.remove.hidden = !picture;
  els.choose.textContent = picture ? "Choose another" : "Choose a picture";
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

els.remove.addEventListener("click", () => {
  picture = null;
  show();
});

whenThemeChanges(showStartField);
