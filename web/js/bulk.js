// The Bulk tab: start a run (a bulk file's prompt over its list of items, each asked with a fresh memory) and watch it. #bulk shows
// the form and the runs; #bulk/<run> shows one run, item by item, while it goes.

import { render } from "./markdown.js";
import { stepText } from "./ask.js";
import { refreshStatus } from "./status.js";

const $ = (id) => document.getElementById(id);
const startArea = $("bulk-start-area");
const runView = $("bulk-run");
const form = $("bulk-form");
const folderInput = $("bulk-folder");
const modelSelect = $("bulk-model");
const thinkingField = $("bulk-thinking-field");
const thinkingSelect = $("bulk-thinking");
const itemsBox = $("bulk-items");
const itemsNote = $("bulk-items-note");
const errorLine = $("bulk-error");
const canEdit = $("bulk-can-edit");

const POLL_MS = 1500;
const LABELS = {
  waiting: "waiting", working: "working", reviewing: "reviewing", done: "done", failed: "failed check", unchanged: "not changed",
  error: "error", stopped: "stopped", undone: "undone", running: "running", stopping: "stopping", paused: "paused",
};
let models = [];
let openRun = "";
let polling = 0;
let filter = "";
let fileName = ""; // the chosen file's name, the run's name when the file has none

const tilde = (p) => (p || "").replace(/^\/Users\/[^/]+/, "~");
const when = (s) => new Date(s * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const minutes = (s) => (s < 90 ? `${Math.round(s)} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);

function showError(text) {
  errorLine.textContent = text;
  errorLine.hidden = !text;
}

// ---------- the form ----------

// A small one to start from (examples/ has fuller ones, with checks and a review).
const EXAMPLE = {
  name: "One-line summaries",
  thinking: "off",
  can_change_files: false,
  prompt: ["Read {file} in {folder}.", "In one sentence, say who talks in it and what happens. Don't change anything."],
  items: [{ file: "lugnut.yarn" }, { file: "snik.yarn" }],
};

async function loadForm() {
  if (models.length) return;
  const m = await fetch("api/models").then((r) => r.json());
  models = m.models;
  modelSelect.innerHTML = "";
  for (const model of models) modelSelect.add(new Option(model.name, model.id));
  $("bulk-folders").innerHTML = m.folders.map((f) => `<option value="${tilde(f.path)}">`).join("");
  modelSelect.value = m.default;
  folderInput.value = localStorage.getItem("codeai-bulk-folder") || "";
  showThinking();
}

// Thinking: the model's Standard choices.
function showThinking(wanted) {
  const keep = wanted || thinkingSelect.value;
  const m = models.find((x) => x.id === modelSelect.value);
  const levels = (m?.thinking || []).filter((t) => t.where === "both" || t.where === "standard");
  thinkingField.hidden = !levels.length;
  thinkingSelect.innerHTML = "";
  for (const t of levels) thinkingSelect.add(new Option(t.label, t.id));
  if (levels.some((t) => t.id === keep)) thinkingSelect.value = keep;
}

// Read the file in the box: say what's in it (the server reads it the same way, and says what's wrong if anything is).
// fill: a new file was loaded, so its model, thinking and Can change files (and a folder, if it has one) fill the form.
function readFile(fill = false) {
  const text = itemsBox.value.trim();
  if (!text) {
    itemsNote.textContent = "";
    return null;
  }
  let data;
  try {
    data = JSON.parse(text);
  } catch (err) {
    itemsNote.textContent = `That isn't valid JSON yet (${err.message}).`;
    return null;
  }
  if (!data || Array.isArray(data) || typeof data !== "object") {
    itemsNote.textContent = 'A bulk file is an object: {"prompt": "...", "items": [...]}.';
    return null;
  }
  const items = data.items;
  if (!Array.isArray(items)) {
    itemsNote.textContent = '"items" should be a list: [{"old": "...", "new": "..."}, ...].';
    return null;
  }
  const n = items.length;
  const prompt = Array.isArray(data.prompt) ? data.prompt.join("\n") : data.prompt || "";
  const parts = [`${n} item${n === 1 ? "" : "s"}`];
  if (!prompt.trim()) parts.push("no prompt yet");
  if (data.checks?.length) parts.push(`${data.checks.length} check${data.checks.length === 1 ? "" : "s"}`);
  if (data.review) parts.push("a review");
  if (data.search) parts.push(`searches for ${data.search} first`);
  // the {fields} the prompt uses that some items don't have (they'd be "(not given)"): a warning, not a stop,
  // since some (a file, a note) are left out on purpose
  const used = [...new Set([...prompt.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].filter((f) => f !== "folder");
  const missing = used
    .map((f) => [f, items.filter((i) => !String(i?.[f] ?? "").trim()).length])
    .filter(([, k]) => k);
  const warn = missing.map(([f, k]) => `{${f}} in ${k === n ? (n === 1 ? "the item" : `all ${n}`) : k}`);
  itemsNote.textContent = `${data.name || fileName ? `${data.name || fileName}: ` : ""}${parts.join(" · ")}.` +
    (warn.length ? ` Not given: ${warn.join(", ")}. Fine if they're optional; otherwise check the items.` : "");
  if (fill) {
    if (data.folder) folderInput.value = data.folder;
    if (data.model && models.some((x) => x.id === data.model)) modelSelect.value = data.model;
    showThinking(data.thinking);
    canEdit.checked = data.can_change_files !== false;
  }
  return data;
}

modelSelect.addEventListener("change", () => showThinking());
itemsBox.addEventListener("input", () => readFile());
itemsBox.addEventListener("paste", () => {
  fileName = "";
  setTimeout(() => readFile(true));
});
$("bulk-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  itemsBox.value = await file.text();
  fileName = file.name.replace(/\.json$/i, "");
  event.target.value = "";
  readFile(true);
});
$("bulk-example").addEventListener("click", () => {
  fileName = "";
  itemsBox.value = JSON.stringify(EXAMPLE, null, 2);
  readFile(true);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("");
  const data = readFile();
  if (data === null) return showError(itemsBox.value.trim() ? itemsNote.textContent : "Add a bulk file first.");
  if (!folderInput.value.trim()) return showError("Pick the folder it works in.");
  const button = $("bulk-start");
  button.disabled = true;
  const body = {
    file: data, folder: folderInput.value.trim(), model: modelSelect.value,
    thinking: thinkingField.hidden ? "" : thinkingSelect.value, can_change_files: canEdit.checked, name: fileName,
  };
  const res = await fetch("api/bulk", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => null);
  button.disabled = false;
  if (!res?.ok) return showError(res ? (await res.json()).detail : "Can't reach CodeAi.");
  localStorage.setItem("codeai-bulk-folder", folderInput.value.trim());
  const run = await res.json();
  itemsBox.value = "";
  fileName = "";
  readFile();
  refreshStatus();
  location.hash = `#bulk/${run.id}`;
});

// ---------- the runs ----------

function countsText(r) {
  const c = r.counts || {};
  const parts = Object.entries(c).filter(([k]) => k !== "waiting").map(([k, v]) => `${v} ${LABELS[k] || k}`);
  if (c.waiting) parts.push(`${c.waiting} to go`);
  return parts.join(" · ");
}

async function loadRuns() {
  const list = $("bulk-runs");
  const runs = await fetch("api/bulk").then((r) => r.json()).catch(() => null);
  if (!runs) return (list.innerHTML = `<p class="muted">Can't reach the server.</p>`);
  if (!runs.length) return (list.innerHTML = `<p class="muted">No runs yet.</p>`);
  list.innerHTML = "";
  for (const r of runs) {
    const row = document.createElement("a");
    row.className = "history-row";
    row.href = `#bulk/${r.id}`;
    row.innerHTML = `<span class="history-open"><strong></strong><span></span></span><span class="chip"></span>`;
    row.querySelector("strong").textContent = r.name;
    row.querySelector(".history-open span").textContent = `${countsText(r)} · ${when(r.created)}`;
    const chip = row.querySelector(".chip");
    chip.textContent = LABELS[r.status] || r.status;
    chip.classList.add(`is-${r.status}`);
    list.append(row);
  }
  // keep the counts moving while a run goes (only while the list is what's shown)
  const token = polling;
  if (runs.some((r) => ["running", "stopping"].includes(r.status)))
    setTimeout(() => token === polling && !openRun && location.hash.startsWith("#bulk") && loadRuns(), POLL_MS * 2);
  return runs;
}

// ---------- one run ----------

function itemTitle(item) {
  return Object.values(item.fields).join(" · ");
}

function itemEl(item, run) {
  const el = document.createElement("details");
  el.className = "run-item";
  el.dataset.n = item.n;
  el.innerHTML = `<summary><span class="n"></span><span class="what"></span><span class="chip"></span></summary>
    <div class="item-body"></div>`;
  fillItem(el, item, run);
  return el;
}

function fillItem(el, item, run) {
  el.querySelector(".n").textContent = item.n;
  el.querySelector(".what").textContent = itemTitle(item);
  const chip = el.querySelector(".chip");
  chip.className = `chip is-${item.status}`;
  chip.textContent = LABELS[item.status] || item.status;
  const key = JSON.stringify([item.status, item.check, item.review, item.undone, item.tries, (item.steps || []).length]);
  if (el.dataset.key === key) return;
  el.dataset.key = key;
  const body = el.querySelector(".item-body");
  const fields = Object.entries(item.fields).map(([k, v]) => `<dt></dt><dd></dd>`).join("");
  body.innerHTML = `<dl class="fields">${fields}</dl><p class="check"></p><div class="answer"></div>
    <details class="thinking steps" hidden><summary></summary><ol class="steps-list"></ol></details>
    <div class="changes-list"></div>
    <div class="changes-actions"><button type="button" class="button small-button undo-button" hidden>Undo this item</button>
      <span class="undo-note muted small"></span></div>
    <div class="item-meta"></div>`;
  const dts = body.querySelectorAll("dt"), dds = body.querySelectorAll("dd");
  Object.entries(item.fields).forEach(([k, v], i) => {
    dts[i].textContent = k;
    dds[i].textContent = v;
  });
  body.querySelector(".check").textContent = [item.check && `Check: ${item.check}`, item.review && `Review: ${item.review}`]
    .filter(Boolean).join("  ·  ");
  body.querySelector(".answer").innerHTML = item.answer ? render(item.answer) : "";
  const steps = item.steps || [];
  const stepsBox = body.querySelector(".steps");
  stepsBox.hidden = !steps.length;
  stepsBox.querySelector("summary").textContent = `Used ${steps.length} tool${steps.length === 1 ? "" : "s"}`;
  stepsBox.querySelector("ol").innerHTML = "";
  for (const s of steps) {
    const li = document.createElement("li");
    li.textContent = `${stepText(s)}: ${s.summary}`;
    if (!s.ok) li.className = "step-failed";
    stepsBox.querySelector("ol").append(li);
  }
  body.querySelector(".changes-list").innerHTML = (item.changes || [])
    .map((f) => render(`**${tilde(f.path)}**${item.undone ? " (undone)" : ""}\n\n\`\`\`diff\n${f.diff || ""}\n\`\`\``))
    .join("");
  const undo = body.querySelector(".undo-button");
  undo.hidden = !(item.changes || []).length || item.undone || ["working", "reviewing"].includes(item.status);
  undo.onclick = async () => {
    undo.disabled = true;
    const res = await fetch(`api/bulk/${run.id}/undo/${item.n}`, { method: "POST" });
    const out = await res.json();
    body.querySelector(".undo-note").textContent = res.ok ? out.notes.join(" ") : out.detail;
    undo.disabled = false;
    poll(run.id, polling);
  };
  body.querySelector(".undo-note").textContent = item.undone && item.undo_notes ? item.undo_notes.join(" ") : "";
  const tries = item.tries > 1 ? ` · ${item.tries} tries` : "";
  body.querySelector(".item-meta").textContent = item.seconds ? `${minutes(item.seconds)} · ${item.tokens} tokens${tries}` : "";
}

function showRun(run) {
  $("run-title").textContent = run.name;
  const chip = $("run-status");
  chip.className = `chip is-${run.status}`;
  chip.textContent = LABELS[run.status] || run.status;
  const total = run.items.length;
  const finished = run.items.filter((i) => !["waiting", "working", "reviewing"].includes(i.status)).length;
  $("run-bar").style.width = `${(100 * finished) / total}%`;
  const counts = {};
  for (const i of run.items) counts[i.status] = (counts[i.status] || 0) + 1;
  const each = finished ? ` · about ${minutes(run.seconds / finished)} an item` : "";
  $("run-counts").textContent = `${finished} of ${total} · ${countsText({ counts })} · ${minutes(run.seconds)} so far${each} · ` +
    `${tilde(run.folder)}, ${models.find((m) => m.id === run.model)?.name || run.model}` +
    `${run.thinking ? `, thinking ${run.thinking}` : ""}`;
  const going = ["running", "stopping"].includes(run.status);
  $("run-stop").hidden = run.status !== "running";
  $("run-carry-on").hidden = going || !run.items.some((i) => ["waiting", "stopped"].includes(i.status));
  $("run-redo").hidden = going || !run.items.some((i) => ["failed", "unchanged", "error"].includes(i.status));
  $("run-undo").hidden = going || !run.items.some((i) => (i.changes || []).length && !i.undone);
  $("run-delete").hidden = going;

  // filter buttons: All, and one per status the run has
  const bar = $("run-filter");
  bar.innerHTML = "";
  for (const [status, n] of [["", total], ...Object.entries(counts)]) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `chip${status ? ` is-${status}` : ""}`;
    b.textContent = `${status ? LABELS[status] || status : "All"} (${n})`;
    b.setAttribute("aria-pressed", String(filter === status));
    b.onclick = () => {
      filter = status;
      showRun(run);
    };
    bar.append(b);
  }

  const list = $("run-items");
  const shown = run.items.filter((i) => !filter || i.status === filter);
  const existing = new Map([...list.children].map((el) => [el.dataset.n, el]));
  if ([...existing.keys()].join() !== shown.map((i) => String(i.n)).join()) {
    list.innerHTML = "";
    for (const item of shown) list.append(existing.get(String(item.n)) || itemEl(item, run));
  }
  for (const item of shown) fillItem(list.querySelector(`[data-n="${item.n}"]`), item, run);
}

async function poll(runId, token) {
  const res = await fetch(`api/bulk/${runId}`).catch(() => null);
  if (token !== polling || openRun !== runId) return;
  if (!res?.ok) {
    $("run-error").textContent = res ? (await res.json()).detail : "Can't reach CodeAi.";
    $("run-error").hidden = false;
    return;
  }
  $("run-error").hidden = true;
  const run = await res.json();
  showRun(run);
  if (["running", "stopping"].includes(run.status)) setTimeout(() => poll(runId, token), POLL_MS);
}

async function act(path, done) {
  const res = await fetch(`api/bulk/${openRun}${path}`, { method: path === "" ? "DELETE" : "POST" }).catch(() => null);
  if (!res?.ok) {
    $("run-error").textContent = res ? (await res.json()).detail : "Can't reach CodeAi.";
    $("run-error").hidden = false;
    return null;
  }
  const out = await res.json();
  done?.(out);
  refreshStatus();
  polling++;
  poll(openRun, polling);
  return out;
}

// asks first, in the page (no pop-ups)
function confirmIt(text, yesLabel, then) {
  $("run-ask-text").textContent = text;
  $("run-ask-yes").textContent = yesLabel;
  $("run-ask").hidden = false;
  $("run-ask-yes").onclick = async () => {
    $("run-ask").hidden = true;
    await then();
  };
}
$("run-ask-no").addEventListener("click", () => ($("run-ask").hidden = true));
$("run-stop").addEventListener("click", () => act("/stop"));
$("run-carry-on").addEventListener("click", () => act("/carry-on"));
$("run-redo").addEventListener("click", () => act("/carry-on?redo=true"));
$("run-undo").addEventListener("click", () =>
  confirmIt("Put back every file this run changed, as it was before?", "Yes, undo it all", () => act("/undo")));
$("run-delete").addEventListener("click", () =>
  confirmIt("Delete this run's record? Files it changed stay as they are (their backups stay in backups/).", "Yes, delete it",
    () => act("", () => (location.hash = "#bulk"))));
$("run-download").addEventListener("click", async () => {
  const run = await fetch(`api/bulk/${openRun}`).then((r) => r.json());
  const out = run.items.map((i) => ({ ...i.fields, status: i.status, check: i.check, review: i.review, answer: i.answer }));
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2)], { type: "application/json" }));
  link.download = `${run.name.replace(/[^\w-]+/g, "-")}-results.json`;
  link.click();
});

export async function showBulk(parts = []) {
  await loadForm();
  openRun = parts[0] || "";
  polling++;
  startArea.hidden = !!openRun;
  runView.hidden = !openRun;
  $("run-ask").hidden = true;
  if (!openRun) return loadRuns();
  filter = "";
  $("run-items").innerHTML = "";
  poll(openRun, polling);
}
