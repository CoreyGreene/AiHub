// Bulk: browse to a folder (inside the allowed ones), then make a model for
// every picture in it. The run's progress shows below until it's finished.

import { api, el, plural, postJson, showError } from "./api.js";

const up = document.getElementById("bulk-up");
const where = document.getElementById("bulk-path");
const folders = document.getElementById("bulk-folders");
const about = document.getElementById("bulk-about");
const sample = document.getElementById("bulk-sample");
const versions = document.getElementById("bulk-versions");
const skip = document.getElementById("bulk-skip");
const go = document.getElementById("bulk-go");
const error = document.getElementById("bulk-error");
const run = document.getElementById("bulk-run");
const runLine = document.getElementById("bulk-line");
const runBar = document.getElementById("bulk-bar");
const stop = document.getElementById("bulk-stop");

let here = null; // the folder on screen
let batch = sessionStorage.getItem("meshai.batch") || "";
let timer = null;

export function showBulk() {
  if (!here) open("");
  watch();
}

async function open(path) {
  showError(error, null);
  try {
    here = await api(`api/browse?path=${encodeURIComponent(path)}`);
  } catch (err) {
    return showError(error, err);
  }
  where.textContent = here.path || "Your folders";
  up.disabled = here.up === null;
  folders.replaceChildren(
    ...here.folders.map((f) => {
      const b = el("button", "folder", f.name);
      b.type = "button";
      b.addEventListener("click", () => open(f.path));
      return b;
    })
  );
  if (here.empty) {
    about.textContent = "No folders are set up yet. Add some to server/settings.local.json under \"folders\".";
  } else if (!here.path) {
    about.textContent = "Choose a folder of pictures.";
  } else {
    about.textContent = here.pictures ? `${plural(here.pictures, "picture")} here.` : "No pictures in this folder.";
  }
  sample.replaceChildren(...(here.sample || []).map((n) => el("span", "", n)));
  if (here.pictures > (here.sample || []).length) sample.append(el("span", "", `+${here.pictures - here.sample.length} more`));
  go.disabled = !here.pictures;
  go.textContent = here.pictures ? `Make all ${here.pictures}` : "Make all";
}

up.addEventListener("click", () => here && here.up !== null && open(here.up));

go.addEventListener("click", async () => {
  showError(error, null);
  go.disabled = true;
  try {
    const data = await postJson("api/bulk", { folder: here.path, versions: Number(versions.value), skip_existing: skip.checked });
    batch = data.batch;
    sessionStorage.setItem("meshai.batch", batch);
    if (!data.jobs) showError(error, new Error(`Nothing to make: all ${plural(data.skipped, "picture")} are already in the Library.`));
    watch();
  } catch (err) {
    showError(error, err);
  } finally {
    go.disabled = !here?.pictures;
  }
});

async function watch() {
  clearTimeout(timer);
  if (!batch) return;
  try {
    const jobs = (await api("api/jobs")).filter((j) => j.batch === batch);
    if (!jobs.length) {
      run.hidden = true;
      return;
    }
    run.hidden = false;
    const done = jobs.filter((j) => j.status === "done").length;
    const failed = jobs.filter((j) => j.status === "failed").length;
    const left = jobs.filter((j) => j.status === "waiting" || j.status === "working");
    const working = jobs.find((j) => j.status === "working");
    runBar.style.width = `${Math.round((100 * (jobs.length - left.length)) / jobs.length)}%`;
    runLine.textContent = `${done} of ${jobs.length} made` + (failed ? `, ${failed} failed` : "") +
      (working ? `. Now: ${working.name}` : left.length ? "" : ". Finished: see the Library.");
    stop.hidden = !left.length;
    if (left.length) timer = setTimeout(watch, 3000);
  } catch {
    timer = setTimeout(watch, 5000);
  }
}

stop.addEventListener("click", async () => {
  try {
    await api(`api/batches/${batch}/stop`, { method: "POST" });
  } finally {
    watch();
  }
});
