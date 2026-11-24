// The Workflows tab: saved lists of picture jobs. Each item is what the
// Advanced or Custom tab would make (prompt, theme or your own model, how
// many) plus a name for where its pictures go in staging. Items are added
// and changed on the Create tab itself (create.js "add mode"), so they
// always look just like it. The diagram shows them as boxes joined by
// arrows, in the order they'll run. Start queues them all; their pictures
// go to Library → Staging, and each box shows how it's going.

import { fillFromItem, setAddMode } from "./create.js";

const choice = document.getElementById("flow-choice");
const newButton = document.getElementById("flow-new");
const newBox = document.getElementById("flow-new-box");
const newName = document.getElementById("flow-new-name");
const newError = document.getElementById("flow-new-error");
const root = document.getElementById("flow");

let flow = null; // the workflow on screen: { id, name, items, running, run }
let themeNames = {}; // theme id -> name, for the boxes
let polling = null; // the timer that asks how a running workflow is going
const POLL_MS = 1500;

function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function button(text, className = "button small-button") {
  const b = el("button", className, text);
  b.type = "button";
  return b;
}

// --- The drop list of workflows, and New ---

export async function loadWorkflows(pickId = null) {
  if (!newBox.hidden) naming(false);
  try {
    const [list, themes] = await Promise.all([
      fetch("api/workflows").then((res) => res.json()),
      fetch("api/themes").then((res) => res.json()),
    ]);
    themeNames = Object.fromEntries(themes.map((t) => [t.id, t.name]));
    const keep = pickId || flow?.id || list[0]?.id;
    choice.replaceChildren(...list.map((f) => new Option(f.name, f.id)));
    choice.parentElement.hidden = !list.length;
    if (!list.length) {
      flow = null;
      root.replaceChildren(el("p", "muted card", "No workflows yet. Tap New to make one."));
      return;
    }
    choice.value = list.some((f) => f.id === keep) ? keep : list[0].id;
    await open(choice.value);
  } catch {
    root.replaceChildren(el("p", "muted card", "Couldn't load the workflows. Is the server running?"));
  }
}

async function open(id) {
  const res = await fetch(`api/workflows/${id}`);
  if (!res.ok) return loadWorkflows();
  flow = await res.json();
  show();
  // While it runs, ask again now and then (only while this tab is shown).
  clearTimeout(polling);
  if (flow.running) {
    polling = setTimeout(() => {
      if (!document.getElementById("view-workflows").hidden && flow?.id === id) open(id);
    }, POLL_MS);
  }
}

choice.addEventListener("change", () => open(choice.value));

// While naming a new workflow, the one on screen is put away, so its
// items can't be mistaken for the new one's.
function naming(on) {
  newBox.hidden = !on;
  root.hidden = on;
  newError.hidden = true;
  if (on) newName.focus();
}

newButton.addEventListener("click", () => naming(newBox.hidden));
document.getElementById("flow-new-cancel").addEventListener("click", () => naming(false));
document.getElementById("flow-new-make").addEventListener("click", async () => {
  const name = newName.value.trim();
  newError.hidden = Boolean(name);
  newError.textContent = "Give it a name first.";
  if (!name) return;
  const res = await fetch("api/workflows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await res.json();
  if (!res.ok) {
    newError.textContent = data.detail;
    newError.hidden = false;
    return;
  }
  newName.value = "";
  naming(false);
  loadWorkflows(data.id);
});

// --- Saving: the whole workflow each time ---

async function save(changed) {
  const res = await fetch(`api/workflows/${flow.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changed),
  });
  const data = await res.json();
  if (!res.ok) return data.detail || "Couldn't save.";
  flow = { ...flow, ...changed };
  return null;
}

// --- The chosen workflow: name, Delete, and the diagram ---

function show() {
  const head = el("section", "card flow-head");
  const nameField = el("label", "field");
  const nameInput = el("input", "text-input");
  nameInput.value = flow.name;
  nameInput.disabled = flow.running;
  nameInput.maxLength = 60;
  nameField.append(el("span", "label", "Name"), nameInput);
  const error = el("p", "error-line");
  error.hidden = true;
  // Renamed when you leave the box (or press Enter).
  nameInput.addEventListener("change", async () => {
    const problem = await save({ name: nameInput.value.trim(), items: flow.items });
    error.textContent = problem || "";
    error.hidden = !problem;
    if (!problem) choice.selectedOptions[0].textContent = flow.name;
  });
  nameInput.addEventListener("keydown", (e) => e.key === "Enter" && nameInput.blur());

  // Delete asks first, right here.
  const remove = button("Delete workflow", "button small-button danger");
  const ask = el("div", "flow-ask");
  ask.hidden = true;
  const yes = button("Yes, delete it", "button small-button danger");
  const no = button("Keep it");
  ask.append(el("p", "", `Delete “${flow.name}” and its ${flow.items.length} item${flow.items.length === 1 ? "" : "s"}? Pictures already made stay.`), yes, no);
  remove.addEventListener("click", () => {
    ask.hidden = false;
    remove.hidden = true;
  });
  no.addEventListener("click", () => {
    ask.hidden = true;
    remove.hidden = false;
  });
  yes.addEventListener("click", async () => {
    await fetch(`api/workflows/${flow.id}`, { method: "DELETE" });
    flow = null;
    loadWorkflows();
  });
  head.append(nameField, error);
  if (!flow.running) head.append(remove, ask); // no deleting while it runs
  root.replaceChildren(head, startCard(), diagram());
}

// Start: every item goes into the queue; pictures go to Library → Staging.
function startCard() {
  const card = el("section", "card flow-start");
  const go = button(flow.running ? "Running…" : flow.run.length ? "Start again" : "Start workflow", "primary");
  go.disabled = flow.running || !flow.items.length;
  const line = el("p", "muted small");
  const error = el("p", "error-line");
  error.hidden = true;
  if (!flow.items.length) line.textContent = "Add an item to start.";
  else if (flow.running) line.textContent = "Making the pictures. You can leave this page; they go to Library → Staging.";
  else if (flow.run.length) line.textContent = "Done. The pictures are in Library → Staging.";
  else line.textContent = `Makes every item in order. Pictures go to Library → Staging, not to a character.`;
  go.addEventListener("click", async () => {
    go.disabled = true;
    const res = await fetch(`api/workflows/${flow.id}/start`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      error.textContent = data.detail || "Couldn't start.";
      error.hidden = false;
      go.disabled = false;
      return;
    }
    open(flow.id);
  });
  card.append(go, line, error);
  return card;
}

// Boxes joined by arrows: one box per item, then "+ Add item".
function diagram() {
  const box = el("section", "flow");
  box.classList.toggle("running", flow.running);
  box.setAttribute("aria-label", "Items, in the order they run");
  flow.items.forEach((item, i) => {
    if (i) box.append(el("span", "flow-arrow"));
    box.append(itemBox(item, i));
  });
  if (flow.running) return box; // no changes while it runs
  if (flow.items.length) box.append(el("span", "flow-arrow"));
  const add = button("+ Add item", "flow-box flow-add");
  add.addEventListener("click", () => startAdding(null));
  box.append(add);
  return box;
}

function itemBox(item, i) {
  const box = el("article", "flow-box");
  const title = el("h3", "", item.name || `${flow.name} ${i + 1}`);
  if (!item.name) title.classList.add("muted");
  const theme = item.custom ? `Custom · ${item.custom.model}` : themeNames[item.theme] || `${item.theme} (not found)`;
  const changed = !item.custom && item.words ? " · own words" : "";
  box.append(
    title,
    el("p", "flow-prompt", item.prompt),
    el("p", "muted small", `${theme}${changed} · ${item.count} picture${item.count === 1 ? "" : "s"}`)
  );

  const run = flow.run[i];
  if (run) box.append(runLine(run));
  if (flow.running) return box;

  const actions = el("div", "flow-actions");
  const edit = button("Edit");
  edit.addEventListener("click", () => startAdding(i));
  const earlier = button("↑", "button small-button");
  earlier.setAttribute("aria-label", "Run earlier");
  earlier.disabled = i === 0;
  earlier.addEventListener("click", () => move(i, -1));
  const later = button("↓", "button small-button");
  later.setAttribute("aria-label", "Run later");
  later.disabled = i === flow.items.length - 1;
  later.addEventListener("click", () => move(i, 1));
  const remove = button("Remove", "button small-button danger");
  remove.addEventListener("click", async () => {
    await save({ name: flow.name, items: flow.items.filter((_, n) => n !== i) });
    show();
  });
  actions.append(edit, earlier, later, remove);
  box.append(actions);
  return box;
}

// How this item's last run went, with a link to its pictures in staging.
function runLine(run) {
  const line = el("p", `flow-run ${run.status}`);
  const made = run.pictures.length;
  const pics = (n) => `${n} picture${n === 1 ? "" : "s"}`;
  if (run.status === "waiting") line.textContent = "Waiting…";
  else if (run.status === "working") {
    const which = run.count > 1 ? `Picture ${run.number} of ${run.count}` : "Working";
    line.textContent = run.stage === "drawing" && run.steps ? `${which} · step ${run.step} of ${run.steps}` : `${which}…`;
  } else if (run.status === "done") {
    line.textContent = made ? `Done: ${pics(made)}${run.blocked ? ` (${run.blocked} not shown)` : ""} ` : "Done ";
  } else line.textContent = run.message || "Didn't work.";
  if (made || run.status === "done") {
    const link = el("a", "", `See in staging: ${run.staging}`);
    link.href = `#library/_staging/${encodeURIComponent(run.folder)}`;
    line.append(link);
  }
  return line;
}

async function move(i, by) {
  const items = [...flow.items];
  [items[i], items[i + by]] = [items[i + by], items[i]];
  await save({ name: flow.name, items });
  show();
}

// --- Adding or changing an item happens on the Create tab ---

function startAdding(index) {
  const id = flow.id;
  const label = index === null ? `Adding to workflow: ${flow.name}` : `Changing item ${index + 1} of ${flow.name}`;
  setAddMode({
    label,
    button: index === null ? "Add to workflow" : "Save changes",
    // Called with the item from the form; returns a problem, or null when saved.
    async done(item) {
      if (flow?.id !== id) await open(id);
      const items = [...flow.items];
      if (index === null) items.push(item);
      else items[index] = item;
      const problem = await save({ name: flow.name, items });
      if (!problem) location.hash = "#workflows";
      return problem;
    },
  });
  fillFromItem(index === null ? null : flow.items[index]);
}
