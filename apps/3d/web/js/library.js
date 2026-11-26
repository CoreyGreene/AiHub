// Library: every model as a card; open one (#library/<slug>) to see it in 3D,
// switch between its versions, download, delete, rename, make more.

import { api, askFirst, el, plural, postJson, showError } from "./api.js";
import { compareWith, stopComparing } from "./compare.js";

const listCard = document.getElementById("library-list-card");
const list = document.getElementById("library-list");
const search = document.getElementById("library-search");
const modelCard = document.getElementById("model-card");
const nameHeading = document.getElementById("model-name");
const viewer = document.getElementById("viewer");
const viewerNote = document.getElementById("viewer-note");
const versionList = document.getElementById("version-list");
const versionInfo = document.getElementById("version-info");
const download = document.getElementById("version-download");
const deleteVersion = document.getElementById("version-delete");
const morePictures = document.getElementById("more-pictures");
const moreCount = document.getElementById("more-count");
const moreGo = document.getElementById("more-go");
const modelError = document.getElementById("model-error");
const deleteModel = document.getElementById("model-delete");
const renameButton = document.getElementById("model-rename");
const renameBox = document.getElementById("rename-box");
const renameInput = document.getElementById("rename-input");
const renameSave = document.getElementById("rename-save");

let everyone = [];
let model = null; // the open model
let chosen = ""; // its shown version id
let timer = null;

export function showLibrary(slug) {
  clearTimeout(timer);
  showError(modelError, null);
  if (slug) return openModel(slug);
  stopComparing();
  model = null;
  modelCard.hidden = true;
  listCard.hidden = false;
  loadList();
}

async function loadList() {
  try {
    everyone = await api("api/models");
    drawList();
    if (everyone.some((m) => m.versions.some(busy))) timer = setTimeout(loadList, 4000);
  } catch (err) {
    list.replaceChildren(el("p", "muted", err.message));
  }
}

const busy = (v) => v.status === "waiting" || v.status === "working";

// PAGE models a page, each shown in 3D (its newest version, turning); the list remembers its page when you open
// a model and come back, and a new search starts at page 1.
const PAGE = 20;
let page = 0;

function drawList() {
  const words = search.value.trim().toLowerCase();
  const found = everyone.filter((m) => m.name.toLowerCase().includes(words));
  if (!found.length) {
    list.replaceChildren(el("p", "muted", everyone.length ? "Nothing matches that." :
      "No models yet. Make one on the Make tab, or many on the Bulk tab."));
    return;
  }
  const pages = Math.ceil(found.length / PAGE);
  page = Math.min(page, pages - 1);
  list.replaceChildren(...found.slice(page * PAGE, (page + 1) * PAGE).map(card));
  if (pages > 1) list.append(pager(pages));
}
search.addEventListener("input", () => {
  page = 0;
  drawList();
});

function pager(pages) {
  const bar = el("nav", "pager");
  bar.setAttribute("aria-label", "Pages");
  const go = (to) => {
    page = to;
    drawList();
    list.scrollIntoView();
  };
  const button = (text, to, cls = "button small-button") => {
    const b = el("button", cls, text);
    b.type = "button";
    b.disabled = to < 0 || to >= pages;
    b.addEventListener("click", () => go(to));
    return b;
  };
  const numbers = el("div", "pager-numbers");
  let last = -1;
  for (let n = 0; n < pages; n++) {
    if (pages > 7 && n > 0 && n < pages - 1 && Math.abs(n - page) > 1) continue;
    if (n - last > 1) numbers.append(el("span", "muted", "…"));
    last = n;
    const b = button(String(n + 1), n, "button small-button page-number");
    if (n === page) b.setAttribute("aria-current", "page");
    numbers.append(b);
  }
  const arrows = el("div", "pager-arrows");
  arrows.append(button("← Previous", page - 1), button("Next →", page + 1));
  bar.append(numbers, arrows);
  return bar;
}

function card(m) {
  const a = el("a", "model");
  a.href = `#library/${encodeURIComponent(m.slug)}`;
  const newest = m.versions.filter((v) => v.status === "done").at(-1);
  let look;
  if (newest) {
    // the model itself, turning slowly; its picture shows until it's loaded
    look = document.createElement("model-viewer");
    look.className = "card-model";
    look.setAttribute("src", newest.url);
    look.setAttribute("poster", m.cover);
    look.setAttribute("loading", "lazy");
    look.setAttribute("auto-rotate", "");
    look.setAttribute("rotation-per-second", "20deg");
    look.setAttribute("interaction-prompt", "none");
    look.setAttribute("environment-image", "neutral");
    look.setAttribute("exposure", "1");
  } else {
    look = el("img");
    look.alt = "";
    look.loading = "lazy";
    look.src = m.cover;
  }
  const making = m.versions.filter(busy).length;
  a.append(look, el("h3", "", m.name),
    el("p", "muted", plural(m.count, "version") + (making ? ` · ${making} being made` : "")));
  return a;
}

async function openModel(slug, keep = "") {
  listCard.hidden = true;
  modelCard.hidden = false;
  renameBox.hidden = true;
  try {
    model = await api(`api/models/${encodeURIComponent(slug)}`);
  } catch {
    location.hash = "#library"; // gone
    return;
  }
  nameHeading.textContent = model.name;
  const done = model.versions.filter((v) => v.status === "done");
  if (!model.versions.some((v) => v.id === chosen) || keep === "") chosen = keep || (done.at(-1) || model.versions.at(-1) || {}).id || "";
  drawVersions();
  drawMorePictures();
  if (model.versions.some(busy)) timer = setTimeout(() => openModel(slug, chosen), 3000);
}

function drawVersions() {
  versionList.replaceChildren(
    ...model.versions.map((v, i) => {
      const b = el("button", "version");
      b.type = "button";
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String(v.id === chosen));
      const img = el("img");
      img.alt = "";
      img.src = v.picture_url;
      const state = v.status === "done" ? "" : v.status === "failed" ? "failed" : v.status === "working" ? "making…" : "waiting";
      b.append(img, el("span", "", `Version ${i + 1}`));
      if (state) b.append(el("span", "state", state));
      b.addEventListener("click", () => {
        chosen = v.id;
        drawVersions();
      });
      return b;
    })
  );
  showChosen();
}

function showChosen() {
  const v = model.versions.find((x) => x.id === chosen);
  const ready = v && v.status === "done";
  if (ready) {
    if (viewer.getAttribute("src") !== v.url) viewer.setAttribute("src", v.url);
    viewerNote.hidden = true;
  } else {
    viewer.removeAttribute("src");
    viewerNote.hidden = false;
    viewerNote.textContent = !v ? "No versions." : v.status === "failed" ? `This version failed: ${v.message || "unknown error"}`
      : "This version is still being made. It appears here when it's done.";
  }
  compareWith(model.name, ready ? v.url : "");
  download.setAttribute("aria-disabled", String(!ready));
  download.href = ready ? v.url : "#";
  download.download = ready ? `${model.slug}-${model.versions.indexOf(v) + 1}.glb` : "";
  deleteVersion.disabled = !v || busy(v);
  versionInfo.textContent = v
    ? [ready && `${Math.round(v.seconds)} s to make`, v.faces && `${v.faces.toLocaleString()} triangles`, `seed ${v.seed}`]
        .filter(Boolean).join(" · ")
    : "";
}

function drawMorePictures() {
  const pics = [...new Set(model.versions.map((v) => v.picture))];
  const current = model.versions.find((v) => v.id === chosen)?.picture || pics[0];
  morePictures.replaceChildren(
    ...pics.map((p) => {
      const label = el("label");
      const radio = el("input");
      radio.type = "radio";
      radio.name = "more-picture";
      radio.value = p;
      radio.checked = p === current;
      const img = el("img");
      img.alt = "From this picture";
      img.src = model.versions.find((v) => v.picture === p).picture_url;
      label.append(radio, img);
      return label;
    })
  );
  morePictures.hidden = pics.length < 2;
}

moreGo.addEventListener("click", async () => {
  showError(modelError, null);
  const picture = morePictures.querySelector("input:checked")?.value || model.versions[0]?.picture;
  moreGo.disabled = true;
  try {
    await postJson(`api/models/${encodeURIComponent(model.slug)}/more`, { picture, versions: Number(moreCount.value) });
    openModel(model.slug, chosen);
  } catch (err) {
    showError(modelError, err);
  } finally {
    moreGo.disabled = false;
  }
});

askFirst(deleteVersion, "Tap again to delete", async () => {
  try {
    const data = await api(`api/models/${encodeURIComponent(model.slug)}/versions/${chosen}`, { method: "DELETE" });
    if (!data.model_left) location.hash = "#library";
    else openModel(model.slug);
  } catch (err) {
    showError(modelError, err);
  }
});

askFirst(deleteModel, "Tap again: delete every version", async () => {
  try {
    await api(`api/models/${encodeURIComponent(model.slug)}`, { method: "DELETE" });
    location.hash = "#library";
  } catch (err) {
    showError(modelError, err);
  }
});

renameButton.addEventListener("click", () => {
  renameBox.hidden = !renameBox.hidden;
  renameInput.value = model.name;
  if (!renameBox.hidden) renameInput.focus();
});
renameSave.addEventListener("click", async () => {
  try {
    const data = await postJson(`api/models/${encodeURIComponent(model.slug)}/rename`, { name: renameInput.value });
    location.hash = `#library/${encodeURIComponent(data.slug)}`;
    openModel(data.slug, chosen);
  } catch (err) {
    showError(modelError, err);
  }
});
