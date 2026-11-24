// Make: choose a picture, name it, how many versions; then watch them being made.

import { api, el, jobLine, showError } from "./api.js";

const drop = document.getElementById("drop");
const fileInput = document.getElementById("make-file");
const preview = document.getElementById("make-preview");
const dropText = document.getElementById("make-drop-text");
const nameInput = document.getElementById("make-name");
const versionsInput = document.getElementById("make-versions");
const go = document.getElementById("make-go");
const error = document.getElementById("make-error");
const progress = document.getElementById("make-progress");
const jobList = document.getElementById("make-jobs");
const openLink = document.getElementById("make-open");

let picture = null; // the chosen File
let watching = []; // job ids made from this tab
let timer = null;

// "item_fridge-2.png" -> "item fridge 2"
const nameFromFile = (file) => file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();

function choose(file) {
  if (!file || !/^image\/(png|jpeg|webp)$/.test(file.type)) {
    showError(error, new Error("Choose a PNG, JPG or WebP picture."));
    return;
  }
  picture = file;
  showError(error, null);
  preview.src = URL.createObjectURL(file);
  preview.hidden = false;
  dropText.hidden = true;
  if (!nameInput.value.trim()) nameInput.value = nameFromFile(file);
}

fileInput.addEventListener("change", () => choose(fileInput.files[0]));
drop.addEventListener("dragover", (e) => {
  e.preventDefault();
  drop.classList.add("over");
});
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  choose(e.dataTransfer.files[0]);
});

go.addEventListener("click", async () => {
  showError(error, null);
  if (!picture) return showError(error, new Error("Choose a picture first."));
  const name = nameInput.value.trim();
  if (!name) return showError(error, new Error("Give the model a name."));
  go.disabled = true;
  try {
    const q = new URLSearchParams({ name, versions: versionsInput.value, filename: picture.name });
    const data = await api(`api/make?${q}`, { method: "POST", body: picture, headers: { "Content-Type": picture.type } });
    watching = data.jobs;
    openLink.href = `#library/${encodeURIComponent(data.slug)}`;
    progress.hidden = false;
    watch();
  } catch (err) {
    showError(error, err);
  } finally {
    go.disabled = false;
  }
});

async function watch() {
  clearTimeout(timer);
  if (!watching.length) return;
  try {
    const jobs = (await api("api/jobs")).filter((j) => watching.includes(j.id));
    jobList.replaceChildren(
      ...jobs.map((j, i) => {
        const row = el("div", `job ${j.status}`);
        row.append(el("strong", "", `${j.name} · version ${i + 1}`), el("span", "muted small", jobLine(j)));
        return row;
      })
    );
    openLink.hidden = !jobs.some((j) => j.status === "done");
    if (jobs.some((j) => j.status === "waiting" || j.status === "working")) timer = setTimeout(watch, 2000);
  } catch {
    timer = setTimeout(watch, 4000);
  }
}

export function showMake() {
  watch();
}
