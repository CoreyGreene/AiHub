// The Pipelines tab: chain saved bulk files, each step working on the files the step before changed. #pipelines
// shows the run form, the builder and the lists; #pipelines/<run> shows one pipeline run, step by step.

import { pick } from "./picker.js";
import { refreshStatus } from "./status.js";

const $ = (id) => document.getElementById(id);
const tilde = (p) => (p || "").replace(/^\/Users\/[^/]+/, "~");
const when = (s) => new Date(s * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const minutes = (s) => (s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
const LABELS = {
  waiting: "waiting", running: "running", done: "done", stopped: "stopped", paused: "paused", error: "error",
  failed: "failed check", unchanged: "not changed", undone: "undone", working: "working", reviewing: "reviewing",
};
const POLL_MS = 2000;

let savedBulk = []; // [{id, name, items}]
let savedPipes = []; // [{id, name, steps}]
let models = [];
let steps = []; // the builder's steps: saved bulk ids
let editing = ""; // the saved pipeline being edited ("" = a new one)
let openRun = "";
let polling = 0;

const bulkName = (id) => savedBulk.find((b) => b.id === id)?.name || `${id} (not saved any more)`;

async function post(url, body, method = "POST") {
  const res = await fetch(url, {
    method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
  }).catch(() => null);
  if (!res) return { error: "Can't reach CodeAi." };
  const out = await res.json();
  return res.ok ? out : { error: out.detail || "That didn't work." };
}

// a Delete button that asks first, in the page: the first click turns it into "Sure? Delete"
function deleteButton(onYes) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "button small-button danger";
  b.textContent = "Delete";
  b.addEventListener("click", async () => {
    if (b.dataset.sure) return onYes(b);
    b.dataset.sure = "1";
    b.textContent = "Sure? Delete";
    setTimeout(() => {
      delete b.dataset.sure;
      b.textContent = "Delete";
    }, 4000);
  });
  return b;
}

// ---------- the lists ----------

async function loadLists() {
  [savedBulk, savedPipes] = await Promise.all([
    fetch("api/saved/bulk").then((r) => r.json()).catch(() => []),
    fetch("api/saved/pipeline").then((r) => r.json()).catch(() => []),
  ]);
  // the run form's pipelines
  const runPick = $("pipe-pick");
  const keep = runPick.value;
  runPick.innerHTML = savedPipes.length ? "" : `<option value="">No pipelines saved yet</option>`;
  for (const p of savedPipes) runPick.add(new Option(p.name, p.id));
  if (savedPipes.some((p) => p.id === keep)) runPick.value = keep;
  showPickedSteps();

  const pipes = $("pipe-saved");
  pipes.innerHTML = savedPipes.length ? "" : `<p class="muted small">None yet: build one below the run form.</p>`;
  for (const p of savedPipes) {
    const el = document.createElement("div");
    el.className = "history-row saved-entry";
    el.innerHTML = `<span class="history-open"><strong></strong><span></span></span>
      <button type="button" class="button small-button">Edit</button>`;
    el.querySelector("strong").textContent = p.name;
    el.querySelector(".history-open span").textContent = p.steps.map((s, i) => `${i + 1}. ${bulkName(s)}`).join("  →  ");
    el.querySelector("button").addEventListener("click", () => edit(p));
    el.append(deleteButton(async () => {
      const out = await post(`api/saved/pipeline/${p.id}`, null, "DELETE");
      if (!out.error) loadLists();
    }));
    pipes.append(el);
  }

  const bulks = $("bulk-saved-list");
  bulks.innerHTML = savedBulk.length ? "" : `<p class="muted small">None yet: on the Bulk tab, open a bulk file and press Save to list.</p>`;
  for (const b of savedBulk) {
    const el = document.createElement("div");
    el.className = "history-row saved-entry";
    el.innerHTML = `<span class="history-open"><strong></strong><span></span></span>`;
    el.querySelector("strong").textContent = b.name;
    el.querySelector(".history-open span").textContent = `${b.items} item${b.items === 1 ? "" : "s"} · saved ${when(b.saved)}`;
    el.append(deleteButton(async () => {
      const out = await post(`api/saved/bulk/${b.id}`, null, "DELETE");
      if (!out.error) loadLists();
    }));
    bulks.append(el);
  }
}

function showPickedSteps() {
  const p = savedPipes.find((x) => x.id === $("pipe-pick").value);
  $("pipe-pick-steps").textContent = p ? p.steps.map((s, i) => `${i + 1}. ${bulkName(s)}`).join("  →  ") : "";
}

async function loadRuns() {
  const list = $("pipe-runs");
  const runs = await fetch("api/pipelines").then((r) => r.json()).catch(() => null);
  if (!runs) return (list.innerHTML = `<p class="muted">Can't reach the server.</p>`);
  if (!runs.length) return (list.innerHTML = `<p class="muted small">No pipeline runs yet.</p>`);
  list.innerHTML = "";
  for (const r of runs) {
    const row = document.createElement("a");
    row.className = "history-row";
    row.href = `#pipelines/${r.id}`;
    row.innerHTML = `<span class="history-open"><strong></strong><span></span></span><span class="chip"></span>`;
    row.querySelector("strong").textContent = r.name;
    const at = r.status === "done" ? `${r.steps.length} steps` : `step ${r.current} of ${r.steps.length}`;
    row.querySelector(".history-open span").textContent = `${at} · ${when(r.created)}`;
    const chip = row.querySelector(".chip");
    chip.textContent = LABELS[r.status] || r.status;
    chip.classList.add(`is-${r.status}`);
    list.append(row);
  }
  const token = polling;
  if (runs.some((r) => r.status === "running"))
    setTimeout(() => token === polling && !openRun && location.hash.startsWith("#pipelines") && loadRuns(), POLL_MS * 2);
}

// ---------- the builder ----------

function drawSteps() {
  const list = $("pipe-steps");
  list.innerHTML = "";
  steps.forEach((id, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="n"></span><span class="what"></span>
      <button type="button" class="button small-button" title="Earlier">↑</button>
      <button type="button" class="button small-button" title="Later">↓</button>
      <button type="button" class="button small-button" title="Take it out">✕</button>`;
    li.querySelector(".n").textContent = `${i + 1}.`;
    li.querySelector(".what").textContent = bulkName(id);
    const [up, down, out] = li.querySelectorAll("button");
    up.disabled = i === 0;
    down.disabled = i === steps.length - 1;
    up.onclick = () => move(i, -1);
    down.onclick = () => move(i, 1);
    out.onclick = () => {
      steps.splice(i, 1);
      drawSteps();
    };
    list.append(li);
  });
}

function move(i, by) {
  [steps[i], steps[i + by]] = [steps[i + by], steps[i]];
  drawSteps();
}

function edit(p) {
  editing = p.id;
  steps = [...p.steps];
  $("pipe-name").value = p.name;
  $("pipe-build-title").textContent = `Editing: ${p.name}`;
  $("pipe-build-note").textContent = "";
  drawSteps();
  $("pipe-name").scrollIntoView({ behavior: "smooth", block: "center" });
}

function newPipeline() {
  editing = "";
  steps = [];
  $("pipe-name").value = "";
  $("pipe-build-title").textContent = "New pipeline";
  $("pipe-build-note").textContent = "";
  drawSteps();
}

// Add step: a list of the saved bulk files; clicking one adds it to the end
function openStepPick() {
  const list = $("step-pick-list");
  list.innerHTML = savedBulk.length ? "" :
    `<p class="muted small">Nothing saved yet: on the Bulk tab, open a bulk file and press Save to list.</p>`;
  for (const b of savedBulk) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "picker-row step-choice";
    row.innerHTML = `<strong></strong><span class="muted small"></span>`;
    row.querySelector("strong").textContent = b.name;
    const used = steps.filter((s) => s === b.id).length;
    row.querySelector("span").textContent =
      `${b.items} item${b.items === 1 ? "" : "s"}${used ? ` · already step ${steps.map((s, i) => (s === b.id ? i + 1 : 0)).filter(Boolean).join(", ")}` : ""}`;
    row.addEventListener("click", () => {
      steps.push(b.id);
      drawSteps();
      $("step-pick").close();
    });
    list.append(row);
  }
  $("step-pick").showModal();
}
$("pipe-add").addEventListener("click", async () => {
  await loadLists(); // anything saved on the Bulk tab since shows up
  openStepPick();
});
$("step-pick-close").addEventListener("click", () => $("step-pick").close());
$("pipe-new").addEventListener("click", newPipeline);
$("pipe-save").addEventListener("click", async () => {
  const note = $("pipe-build-note");
  const name = $("pipe-name").value.trim();
  if (!name) return (note.textContent = "Give it a name first.");
  if (!steps.length) return (note.textContent = "Add at least one step.");
  const text = JSON.stringify({ name, steps }, null, 2);
  const out = await post("api/saved/pipeline", { name, text });
  if (out.error) return (note.textContent = out.error);
  // renamed: the old file goes, so it isn't listed twice
  if (editing && editing !== out.id) await post(`api/saved/pipeline/${editing}`, null, "DELETE");
  editing = out.id;
  $("pipe-build-title").textContent = `Editing: ${name}`;
  note.textContent = `Saved${out.replaced ? " (it replaced the one saved before)" : ""}.`;
  await loadLists();
  $("pipe-pick").value = out.id;
  showPickedSteps();
});

// ---------- the run form ----------

function setFolder(which, path) {
  const el = $(`pipe-${which}-shown`);
  el.dataset.path = path || "";
  el.textContent = path ? tilde(path) : "No folder yet";
  el.classList.toggle("muted", !path);
}

$("pipe-input-choose").addEventListener("click", async () => {
  const path = await pick({ mode: "folder", start: $("pipe-input-shown").dataset.path, title: "Pick the input folder" });
  if (path) setFolder("input", path);
});
$("pipe-output-choose").addEventListener("click", async () => {
  const path = await pick({ mode: "folder", start: $("pipe-output-shown").dataset.path, title: "Pick the output folder" });
  if (path) setFolder("output", path);
});
$("pipe-pick").addEventListener("change", showPickedSteps);
$("pipe-model").addEventListener("change", showThinking);

function showThinking() {
  const m = models.find((x) => x.id === $("pipe-model").value);
  const sel = $("pipe-thinking");
  sel.innerHTML = "";
  sel.add(new Option("Each bulk file's own", ""));
  for (const t of m?.thinking || []) sel.add(new Option(t.label, t.id));
}

$("pipe-run-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = $("pipe-run-error");
  const say = (text) => {
    error.textContent = text;
    error.hidden = !text;
  };
  say("");
  const body = {
    pipeline: $("pipe-pick").value, input: $("pipe-input-shown").dataset.path || "",
    output: $("pipe-output-shown").dataset.path || "", model: $("pipe-model").value, thinking: $("pipe-thinking").value,
  };
  if (!body.pipeline) return say("Save a pipeline first (below).");
  if (!body.input) return say("Pick the input folder.");
  if (!body.output) return say("Pick the output folder.");
  $("pipe-start").disabled = true;
  const out = await post("api/pipelines", body);
  $("pipe-start").disabled = false;
  if (out.error) return say(out.error);
  localStorage.setItem("codeai-pipe-input", body.input);
  localStorage.setItem("codeai-pipe-output", body.output);
  refreshStatus();
  location.hash = `#pipelines/${out.id}`;
});

async function loadForm() {
  if (models.length) return;
  const m = await fetch("api/models").then((r) => r.json());
  models = m.models;
  const sel = $("pipe-model");
  sel.innerHTML = "";
  sel.add(new Option("Each bulk file's own", ""));
  for (const model of models) sel.add(new Option(model.name, model.id));
  showThinking();
  setFolder("input", localStorage.getItem("codeai-pipe-input") || "");
  setFolder("output", localStorage.getItem("codeai-pipe-output") || "");
}

// ---------- one pipeline run ----------

function countsText(s) {
  const c = s.counts || {};
  const parts = Object.entries(c).filter(([k]) => k !== "waiting").map(([k, v]) => `${v} ${LABELS[k] || k}`);
  if (c.waiting) parts.push(`${c.waiting} to go`);
  return parts.join(" · ");
}

function showRun(run) {
  $("pipe-run-title").textContent = run.name;
  const chip = $("pipe-run-status");
  chip.className = `chip is-${run.status}`;
  chip.textContent = LABELS[run.status] || run.status;
  const last = run.steps[run.steps.length - 1];
  $("pipe-run-where").textContent = `From ${tilde(run.input)} (the originals aren't touched) · result in ${tilde(last.output)}` +
    `${run.model ? ` · ${models.find((m) => m.id === run.model)?.name || run.model}` : ""} · started ${when(run.created)}`;
  $("pipe-run-stop").hidden = run.status !== "running";
  $("pipe-run-carry-on").hidden = !["stopped", "paused", "error"].includes(run.status);
  $("pipe-run-delete").hidden = run.status === "running";
  const err = $("pipe-run-error-line");
  err.textContent = run.error || "";
  err.hidden = !run.error;

  const list = $("pipe-run-steps");
  list.innerHTML = "";
  run.steps.forEach((s, i) => {
    if (i) {
      const arrow = document.createElement("li");
      arrow.className = "arrow";
      arrow.textContent = "↓ its changed files are the next step's input";
      list.append(arrow);
    }
    const li = document.createElement("li");
    li.innerHTML = `<div class="step-head"><span class="n"></span><strong></strong><span class="chip"></span></div>
      <span class="muted small counts"></span><span class="muted small where"></span><span class="muted small out"></span>`;
    li.querySelector(".n").textContent = `${s.n}.`;
    li.querySelector("strong").textContent = s.name;
    const status = s.run_status && s.status !== "error" ? s.run_status : s.status;
    const c = li.querySelector(".chip");
    c.className = `chip is-${status}`;
    c.textContent = LABELS[status] || status;
    li.querySelector(".counts").textContent = s.total ? `${countsText(s)} of ${s.total} · ${minutes(s.seconds || 0)}` : "";
    li.querySelector(".where").textContent = s.folder ? `Works on: ${tilde(s.folder)}` : "";
    li.querySelector(".out").textContent = `Changed files: ${tilde(s.output)}${s.run ? ` (${s.copied || 0} so far)` : ""}`;
    if (s.run) {
      const a = document.createElement("a");
      a.href = `#bulk/${s.run}`;
      a.className = "small";
      a.textContent = "Open this step's run (every item, its diffs, undo)";
      li.append(a);
    }
    list.append(li);
  });
}

async function poll(runId, token) {
  const res = await fetch(`api/pipelines/${runId}`).catch(() => null);
  if (token !== polling || openRun !== runId) return;
  if (!res?.ok) {
    $("pipe-run-error-line").textContent = res ? (await res.json()).detail : "Can't reach CodeAi.";
    $("pipe-run-error-line").hidden = false;
    return;
  }
  const run = await res.json();
  showRun(run);
  if (run.status === "running") setTimeout(() => poll(runId, token), POLL_MS);
}

async function act(path, method = "POST") {
  const out = await post(`api/pipelines/${openRun}${path}`, null, method);
  if (out.error) {
    $("pipe-run-error-line").textContent = out.error;
    $("pipe-run-error-line").hidden = false;
    return null;
  }
  refreshStatus();
  polling++;
  poll(openRun, polling);
  return out;
}

$("pipe-run-stop").addEventListener("click", () => act("/stop"));
$("pipe-run-carry-on").addEventListener("click", () => act("/carry-on"));
$("pipe-run-delete").addEventListener("click", async (event) => {
  const b = event.currentTarget;
  if (!b.dataset.sure) {
    b.dataset.sure = "1";
    b.textContent = "Sure? Delete the record";
    setTimeout(() => {
      delete b.dataset.sure;
      b.textContent = "Delete";
    }, 4000);
    return;
  }
  const out = await post(`api/pipelines/${openRun}`, null, "DELETE");
  if (!out.error) location.hash = "#pipelines";
});

export async function showPipelines(parts = []) {
  await loadForm();
  openRun = parts[0] || "";
  polling++;
  $("pipe-start-area").hidden = !!openRun;
  $("pipe-run").hidden = !openRun;
  await loadLists();
  if (!openRun) return loadRuns();
  poll(openRun, polling);
}
