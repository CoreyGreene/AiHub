// The Experiments tab: batches of prompts, each with its own model, made one after another to compare.
// #experiments shows the experiment being changed and its runs; #experiments/run/<id> one run, with a
// grid of its pictures (a row per prompt, a column per batch). The server does the work
// (server/experiments.py); this page only edits the list and shows the pictures.

import { openViewer } from "./viewer.js";

const $ = (id) => document.getElementById(id);
const tilde = (p) => (p || "").replace(/^\/Users\/[^/]+/, "~");
const when = (s) => new Date(s * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const POLL_MS = 3000;
const STATUS = { working: "making", waiting: "waiting", done: "done", stopped: "stopped", running: "running" };

let models = [];
let saved = [];
let current = null; // the experiment being changed: {id, name, seed, batches}
let pollToken = 0;

async function call(url, method = "GET", body) {
  const res = await fetch(url, {
    method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined,
  }).catch(() => null);
  if (!res) return { error: "Can't reach the server." };
  const out = await res.json().catch(() => ({}));
  return res.ok ? out : { error: out.detail || "That didn't work." };
}

function showError(id, text) {
  $(id).textContent = text || "";
  $(id).hidden = !text;
}

// A button that asks first, in the page: the first tap turns it into "Sure?"
function askFirst(button, onYes) {
  const label = button.textContent;
  button.onclick = () => {
    if (button.dataset.sure) return onYes();
    button.dataset.sure = "1";
    button.textContent = "Sure? Tap again";
    setTimeout(() => {
      delete button.dataset.sure;
      button.textContent = label;
    }, 4000);
  };
}

// ---------- the experiment being changed ----------

const blankBatch = (model = "") => ({ name: "", model, prompts: [], count: 1, width: 0, height: 0, steps: 0, guidance: 0, negative: "" });
const firstModel = () => (models.find((m) => m.here) || models[0] || {}).id || "";
const modelOf = (id) => models.find((m) => m.id === id);

function readBatches() {
  // What's typed in the page, back into current.batches
  document.querySelectorAll("#exp-batches .exp-batch").forEach((el, i) => {
    const b = current.batches[i];
    const val = (name) => el.querySelector(`[data-k="${name}"]`).value;
    b.name = val("name").trim();
    b.model = val("model");
    b.prompts = val("prompts").split("\n").map((p) => p.trim()).filter(Boolean);
    for (const k of ["count", "width", "height", "steps", "guidance"]) b[k] = Number(val(k)) || 0;
    b.negative = val("negative").trim();
  });
}

function drawBatches() {
  const box = $("exp-batches");
  box.innerHTML = "";
  current.batches.forEach((b, i) => {
    const el = document.createElement("fieldset");
    el.className = "exp-batch";
    el.innerHTML = `
      <legend class="label">Batch ${i + 1}</legend>
      <label class="field"><span class="label">Model</span><select class="text-input" data-k="model"></select></label>
      <label class="field"><span class="label">Name <span class="optional muted">(optional: the model's name)</span></span>
        <input class="text-input" type="text" maxlength="60" data-k="name" autocomplete="off"></label>
      <label class="field"><span class="label">Prompts, one a line</span>
        <textarea rows="5" data-k="prompts" placeholder="A rusty robot with a lantern, full body, plain grey background"></textarea></label>
      <div class="exp-numbers">
        <label class="field"><span class="label">Pictures a prompt</span><input class="text-input" type="number" min="1" max="20" inputmode="numeric" data-k="count"></label>
        <label class="field"><span class="label">Steps</span><input class="text-input" type="number" min="1" max="150" inputmode="numeric" data-k="steps"></label>
        <label class="field"><span class="label">Width</span><input class="text-input" type="number" step="16" inputmode="numeric" data-k="width"></label>
        <label class="field"><span class="label">Height</span><input class="text-input" type="number" step="16" inputmode="numeric" data-k="height"></label>
        <label class="field"><span class="label">Guidance</span><input class="text-input" type="number" step="0.1" inputmode="decimal" data-k="guidance"></label>
      </div>
      <label class="field exp-negative"><span class="label">Leave out <span class="optional muted">(negative prompt, optional)</span></span>
        <input class="text-input" type="text" data-k="negative" autocomplete="off" placeholder="blurry, text, watermark"></label>
      <p class="muted small exp-model-note"></p>
      <div class="exp-batch-tools">
        <button type="button" class="button small-button" data-do="up">↑</button>
        <button type="button" class="button small-button" data-do="down">↓</button>
        <button type="button" class="button small-button" data-do="copy">Copy with another model</button>
        <button type="button" class="button small-button danger" data-do="remove">Remove</button>
      </div>`;
    const pick = el.querySelector('[data-k="model"]');
    for (const m of models) {
      const opt = new Option(m.here ? m.name : `${m.name} (not here yet)`, m.id);
      opt.disabled = !m.here && m.id !== b.model;
      pick.add(opt);
    }
    if (b.model && !modelOf(b.model)) pick.add(new Option(`${b.model} (not here)`, b.model));
    pick.value = b.model || firstModel();
    el.querySelector('[data-k="name"]').value = b.name || "";
    el.querySelector('[data-k="prompts"]').value = (b.prompts || []).join("\n");
    el.querySelector('[data-k="count"]').value = b.count || 1;
    for (const k of ["width", "height", "steps", "guidance"]) el.querySelector(`[data-k="${k}"]`).value = b[k] || "";
    el.querySelector('[data-k="negative"]').value = b.negative || "";
    const showModel = () => {
      const m = modelOf(pick.value);
      for (const k of ["width", "height", "steps", "guidance"])
        el.querySelector(`[data-k="${k}"]`).placeholder = m ? `${m.defaults[k]}` : "";
      el.querySelector(".exp-negative").hidden = m ? !m.negative : false;
      el.querySelector(".exp-model-note").textContent = m
        ? `Empty boxes use ${m.name}'s own: ${m.defaults.width}×${m.defaults.height}, ${m.defaults.steps} steps, guidance ${m.defaults.guidance}.${m.negative ? "" : " It has no negative prompt."}`
        : "";
    };
    pick.addEventListener("change", showModel);
    showModel();
    el.querySelector('[data-do="up"]').disabled = i === 0;
    el.querySelector('[data-do="down"]').disabled = i === current.batches.length - 1;
    el.querySelectorAll("[data-do]").forEach((btn) => btn.addEventListener("click", () => batchTool(btn.dataset.do, i)));
    box.append(el);
  });
  if (!current.batches.length) box.innerHTML = `<p class="muted small">No batches yet.</p>`;
}

function batchTool(what, i) {
  readBatches();
  const list = current.batches;
  if (what === "up" || what === "down") {
    const j = what === "up" ? i - 1 : i + 1;
    [list[i], list[j]] = [list[j], list[i]];
  } else if (what === "remove") {
    list.splice(i, 1);
  } else if (what === "copy") {
    // The same prompts, pictures and size with the next model not used yet; its own steps and guidance.
    const used = new Set(list.map((b) => b.model));
    const next = models.find((m) => m.here && !used.has(m.id)) || modelOf(list[i].model);
    list.splice(i + 1, 0, { ...list[i], prompts: [...list[i].prompts], name: "", model: next?.id || "", steps: 0, guidance: 0 });
  }
  drawBatches();
}

function showExperiment(exp) {
  current = exp;
  $("exp-name").value = exp.name || "";
  $("exp-choice").value = exp.id || "";
  $("exp-delete").hidden = !exp.id;
  $("exp-note").textContent = exp.id && exp.seed ? `Seeds start at ${exp.seed}, the same for every batch.` : "";
  showError("exp-error", "");
  drawBatches();
  loadRuns();
}

function newExperiment() {
  showExperiment({ id: "", name: "", seed: 0, batches: [blankBatch(firstModel())] });
}

async function save() {
  readBatches();
  current.name = $("exp-name").value.trim();
  const body = { name: current.name, seed: current.seed, batches: current.batches };
  const out = current.id ? await call(`api/experiments/${current.id}`, "PUT", body) : await call("api/experiments", "POST", body);
  if (out.error) {
    showError("exp-error", out.error);
    return null;
  }
  showError("exp-error", "");
  await loadList(out.id);
  return out.id;
}

async function loadList(choose) {
  const out = await call("api/experiments");
  if (out.error) return showError("exp-error", out.error);
  ({ models } = out);
  saved = out.experiments;
  const pick = $("exp-choice");
  pick.innerHTML = "";
  pick.add(new Option(saved.length ? "A new experiment" : "A new experiment (none saved yet)", ""));
  for (const e of saved) pick.add(new Option(`${e.name} (${e.batches} batch${e.batches === 1 ? "" : "es"})`, e.id));
  const id = choose ?? current?.id ?? localStorage.getItem("imageai-experiment") ?? "";
  if (id && saved.some((e) => e.id === id)) {
    localStorage.setItem("imageai-experiment", id);
    const exp = await call(`api/experiments/${id}`);
    if (!exp.error) return showExperiment(exp);
  }
  if (!current || current.id) newExperiment();
  else showExperiment(current);
}

$("exp-choice").addEventListener("change", () => {
  const id = $("exp-choice").value;
  localStorage.setItem("imageai-experiment", id);
  if (!id) return newExperiment();
  loadList(id);
});
$("exp-new").addEventListener("click", () => {
  localStorage.setItem("imageai-experiment", "");
  newExperiment();
  $("exp-name").focus();
});
$("exp-add").addEventListener("click", () => {
  readBatches();
  const last = current.batches.at(-1);
  current.batches.push(last ? { ...blankBatch(last.model), prompts: [...last.prompts], count: last.count } : blankBatch(firstModel()));
  drawBatches();
});
$("exp-save").addEventListener("click", async () => {
  if (await save()) $("exp-note").textContent = "Saved.";
});
$("exp-start").addEventListener("click", async () => {
  const id = await save();
  if (!id) return;
  const out = await call(`api/experiments/${id}/start`, "POST");
  if (out.error) return showError("exp-error", out.error);
  location.hash = `#experiments/run/${out.run}`;
});
askFirst($("exp-delete"), async () => {
  const out = await call(`api/experiments/${current.id}`, "DELETE");
  if (out.error) return showError("exp-error", out.error);
  localStorage.setItem("imageai-experiment", "");
  current = null;
  loadList("");
});

async function loadRuns() {
  const out = await call("api/experiments");
  const box = $("exp-runs");
  if (out.error) return (box.innerHTML = `<p class="muted">${out.error}</p>`);
  const runs = current?.id ? out.runs.filter((r) => r.experiment === current.id) : out.runs;
  if (!runs.length) return (box.innerHTML = `<p class="muted small">${current?.id ? "This experiment hasn't run yet." : "No runs yet."}</p>`);
  box.innerHTML = "";
  for (const r of runs) {
    const a = document.createElement("a");
    a.className = "exp-run-row";
    a.href = `#experiments/run/${r.id}`;
    a.innerHTML = `<span><strong></strong><span class="muted small"></span></span><span class="exp-chip"></span>`;
    a.querySelector("strong").textContent = r.name;
    a.querySelector(".muted").textContent = `${when(r.created)} · ${r.batches} batch${r.batches === 1 ? "" : "es"} · ${r.made} of ${r.total} pictures`;
    const chip = a.querySelector(".exp-chip");
    chip.textContent = STATUS[r.status] || r.status;
    chip.dataset.status = r.status;
    box.append(a);
  }
  const token = pollToken;
  if (runs.some((r) => r.status === "running"))
    setTimeout(() => token === pollToken && !$("exp-edit-area").hidden && loadRuns(), POLL_MS * 2);
}

// ---------- one run ----------

async function showRun(runId) {
  const token = ++pollToken;
  const run = await call(`api/experiment-runs/${runId}`);
  if (token !== pollToken) return;
  if (run.error) {
    $("run-title").textContent = "Run not found";
    showError("run-error", run.error);
    return;
  }
  showError("run-error", "");
  $("run-title").textContent = run.name;
  const made = run.batches.reduce((n, b) => n + b.made, 0);
  const total = run.batches.reduce((n, b) => n + b.total, 0);
  $("run-line").textContent = `${when(run.created)} · ${STATUS[run.status] || run.status} · ${made} of ${total} pictures · seeds from ${run.seed}`;
  $("run-path").textContent = tilde(run.path);
  $("run-stop").hidden = run.status !== "running";
  $("run-delete").hidden = run.status === "running";

  const list = $("run-batches");
  list.innerHTML = "";
  for (const b of run.batches) {
    const li = document.createElement("li");
    li.innerHTML = `<div class="exp-batch-head"><strong></strong><span class="exp-chip"></span></div>
      <span class="muted small exp-batch-line"></span><span class="muted small exp-path"></span>`;
    li.querySelector("strong").textContent = `${b.n}. ${b.name}`;
    const chip = li.querySelector(".exp-chip");
    chip.dataset.status = b.status;
    chip.textContent = b.status === "working" && b.stage === "drawing" && b.steps ? `step ${b.step} of ${b.steps}`
      : b.status === "working" && b.stage === "loading" ? "loading the model" : STATUS[b.status] || b.status;
    const s = b.settings;
    const bits = [b.model_name, `${b.made} of ${b.total}`, `${s.width}×${s.height}, ${s.steps} steps, guidance ${s.guidance}`];
    if (b.seconds != null) bits.push(`${b.seconds} s a picture`);
    if (b.first_seconds != null) bits.push(`first ${b.first_seconds} s with loading`);
    li.querySelector(".exp-batch-line").textContent = bits.join(" · ");
    li.querySelector(".exp-path").textContent = tilde(b.path);
    for (const p of b.problems) {
      const err = document.createElement("span");
      err.className = "error-line";
      err.textContent = p;
      li.append(err);
    }
    list.append(li);
  }
  drawCompare(run);
  if (run.status === "running")
    setTimeout(() => token === pollToken && location.hash === `#experiments/run/${runId}` && showRun(runId), POLL_MS);
}

function drawCompare(run) {
  // Rows: every prompt any batch had (in order); columns: the batches.
  const prompts = [];
  for (const b of run.batches) for (const p of b.prompts) if (!prompts.includes(p)) prompts.push(p);
  const table = $("run-compare");
  table.innerHTML = "";
  const head = table.createTHead().insertRow();
  head.insertCell().textContent = "Prompt";
  for (const b of run.batches) head.insertCell().textContent = `${b.n}. ${b.name}`;
  const body = table.createTBody();
  prompts.forEach((prompt) => {
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.className = "exp-prompt";
    cell.textContent = prompt;
    const rowPictures = [];
    const cells = run.batches.map((b) => {
      const n = b.prompts.indexOf(prompt) + 1;
      const pics = n ? b.pictures.filter((p) => p.prompt_number === n) : [];
      return { b, n, pics };
    });
    for (const c of cells) for (const p of c.pics) rowPictures.push({ image: p.image });
    for (const { b, n, pics } of cells) {
      const td = row.insertCell();
      if (!n) td.innerHTML = `<span class="muted small">not in this batch</span>`;
      else if (!pics.length) td.innerHTML = `<span class="muted small">${b.status === "stopped" || b.status === "done" ? "none" : "…"}</span>`;
      for (const p of pics) {
        const img = document.createElement("img");
        img.src = p.image;
        img.loading = "lazy";
        img.alt = `${b.name}: ${prompt}`;
        img.title = p.seconds != null ? `seed ${p.seed} · ${p.seconds} s` : `seed ${p.seed}`;
        img.addEventListener("click", () => openViewer(rowPictures, rowPictures.findIndex((r) => r.image === p.image)));
        td.append(img);
      }
    }
  });
}

$("run-stop").addEventListener("click", async () => {
  const id = location.hash.split("/")[2];
  const out = await call(`api/experiment-runs/${id}/stop`, "POST");
  if (out.error) return showError("run-error", out.error);
  showRun(id);
});
askFirst($("run-delete"), async () => {
  const id = location.hash.split("/")[2];
  const out = await call(`api/experiment-runs/${id}`, "DELETE");
  if (out.error) return showError("run-error", out.error);
  location.hash = "#experiments";
});

// #experiments, or #experiments/run/<id>
export function showExperiments(sub, more) {
  const isRun = sub === "run" && more;
  $("exp-edit-area").hidden = isRun;
  $("exp-run-area").hidden = !isRun;
  pollToken++;
  if (isRun) showRun(more);
  else loadList();
}
