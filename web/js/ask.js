// The Ask tab: pick a model, ask, and watch the answer being written. Asking again carries the conversation on;
// "New conversation" starts a fresh one. The address is #ask/<conversation>, so History can open one here.
// Standard and Advanced are the same form; Advanced adds more Thinking levels (#ask/advanced/<conversation>).

import { render } from "./markdown.js";
import { refreshStatus } from "./status.js";

const form = document.getElementById("ask-form");
const modelSelect = document.getElementById("model");
const modelNote = document.getElementById("model-note");
const thinkingField = document.getElementById("thinking-field");
const thinkingSelect = document.getElementById("thinking");
const canEdit = document.getElementById("can-edit");
const prompt = document.getElementById("prompt");
const promptLabel = document.getElementById("prompt-label");
const promptError = document.getElementById("prompt-error");
const askButton = document.getElementById("ask-button");
const newButton = document.getElementById("new-button");
const stopButton = document.getElementById("stop-button");
const thread = document.getElementById("thread");
const title = document.getElementById("result-title");

const POLL_MS = 400;
let models = [];
let conversation = "";   // the open conversation's id ("" = a new one)
let job = "";            // the question being answered now
let following = 0;       // bumps when we stop following, so an old poll loop ends
let mode = "standard";   // the sub-tab: standard or advanced

// The address for a conversation in this sub-tab.
const address = (conv, inMode = mode) => `#ask${inMode === "advanced" ? "/advanced" : ""}${conv ? `/${conv}` : ""}`;

// ---------- models ----------

export async function loadModels() {
  const res = await fetch("api/models");
  const data = await res.json();
  models = data.models;
  modelSelect.innerHTML = "";
  if (!models.length) {
    modelSelect.innerHTML = "<option>No models found</option>";
    modelNote.textContent = "Add one to server/settings.local.json, then restart.";
    askButton.disabled = true;
    return;
  }
  for (const m of models) modelSelect.add(new Option(m.name, m.id));
  const saved = localStorage.getItem("codeai-model");
  modelSelect.value = models.some((m) => m.id === saved) ? saved : data.default;
  showNote();
}

// The model's note, and its Thinking choices for this sub-tab (hidden for a model that has none). The choice is
// kept per model and sub-tab.
const thinkingKey = () => `codeai-thinking-${mode}-${modelSelect.value}`;

function showNote() {
  const m = models.find((x) => x.id === modelSelect.value);
  modelNote.textContent = m?.note || "";
  const levels = (m?.thinking || []).filter((t) => t.where === "both" || t.where === mode);
  thinkingField.hidden = !levels.length;
  thinkingSelect.innerHTML = "";
  for (const t of levels) thinkingSelect.add(new Option(t.label, t.id));
  const saved = localStorage.getItem(thinkingKey());
  if (levels.some((t) => t.id === saved)) thinkingSelect.value = saved;
}

modelSelect.addEventListener("change", () => {
  localStorage.setItem("codeai-model", modelSelect.value);
  showNote();
});

thinkingSelect.addEventListener("change", () => {
  localStorage.setItem(thinkingKey(), thinkingSelect.value);
});

// ---------- the conversation on screen ----------

function questionEl(text, from, edits) {
  const el = document.createElement("div");
  el.className = "question";
  const tags = [from === "claude" ? "Claude asked" : "", edits ? "can change files" : ""].filter(Boolean);
  if (tags.length) {
    const tag = document.createElement("span");
    tag.className = "from";
    tag.textContent = tags.join(" · ");
    el.append(tag);
  }
  el.append(text);
  return el;
}

// An answer: its thinking (folded away), the answer, and a line with the model, time and speed.
function answerEl() {
  const el = document.createElement("div");
  el.className = "answer-box";
  el.innerHTML = `
    <details class="thinking" hidden><summary><span class="live-dot" hidden></span><span class="thinking-label">Thinking</span></summary>
      <div class="thinking-text"></div></details>
    <details class="thinking steps" hidden><summary class="steps-label"></summary><ol class="steps-list"></ol></details>
    <div class="answer"></div>
    <div class="changes" hidden>
      <details class="thinking"><summary class="changes-label"></summary><div class="changes-list"></div></details>
      <div class="changes-actions"><button type="button" class="button small-button undo-button">Undo these changes</button>
        <span class="undo-note muted small"></span></div>
    </div>
    <div class="answer-meta"></div>`;
  return el;
}

function fillAnswer(el, a, live) {
  const thinking = el.querySelector(".thinking");
  thinking.hidden = !(a.thinking || "").trim();
  el.querySelector(".thinking-text").textContent = a.thinking || "";
  el.querySelector(".live-dot").hidden = !(live && a.status === "thinking");
  el.querySelector(".thinking-label").textContent = live && a.status === "thinking" ? "Thinking…" : "Thinking";
  showSteps(el, a.steps || [], live && a.status === "looking");
  showChanges(el, a, live);
  const answer = el.querySelector(".answer");
  answer.classList.toggle("failed", a.status === "failed");
  const text = a.content ?? a.answer ?? "";
  if (live && !text) {
    const what = {
      waiting: a.ahead ? `Waiting: ${a.ahead} question${a.ahead > 1 ? "s" : ""} ahead of this one` : "Waiting…",
      loading: "Loading the model (20-60 seconds the first time)…",
      thinking: "Thinking before it answers…",
      looking: "Looking at your files…",
    }[a.status] || "Working…";
    answer.innerHTML = `<div class="waiting-line"><span class="spinner"></span><span></span></div>`;
    answer.querySelector(".waiting-line span:last-child").textContent = what;
  } else {
    answer.innerHTML = render(a.status === "failed" ? `Something went wrong: ${text || a.message}` : text);
  }
  const meta = el.querySelector(".answer-meta");
  const parts = [];
  if (a.model_name || (!live && a.model)) parts.push(a.model_name || a.model);
  if (a.seconds) parts.push(`${Math.round(a.seconds)} s`);
  if (a.per_second) parts.push(`${a.per_second} tokens/s`);
  if (a.status === "stopped") parts.push("stopped");
  meta.textContent = parts.join(" · ");
  if (a.message && a.status !== "failed" && a.status !== "stopped") {
    const note = document.createElement("span");
    note.className = "note-line";
    note.textContent = a.message;
    meta.append(note);
  }
}

// What it looked at: one line per tool it used ("Read ~/Desktop/notes.txt: 40 lines").
const VERB = { list_files: "Listed", find_files: "Looked for", read_file: "Read", search: "Searched" };

function stepText(s) {
  const a = s.arguments || {};
  const where = (a.path || "").replace(/^\/Users\/[^/]+/, "~");
  if (s.tool === "find_files") return `Looked for "${a.name}" in ${where}`;
  if (s.tool === "search") return `Searched ${where} for "${a.pattern}"`;
  return `${VERB[s.tool] || s.tool} ${where}`;
}

function showSteps(el, steps, live) {
  const box = el.querySelector(".steps");
  box.hidden = !steps.length;
  if (!steps.length) return;
  el.querySelector(".steps-label").textContent =
    `${live ? "Looking at" : "Looked at"} ${steps.length} thing${steps.length > 1 ? "s" : ""}${live ? "…" : ""}`;
  const list = el.querySelector(".steps-list");
  list.innerHTML = "";
  for (const s of steps) {
    const li = document.createElement("li");
    li.textContent = `${stepText(s)}: ${s.summary}`;
    if (!s.ok) li.className = "step-failed";
    list.append(li);
  }
}

// The files an answer changed: each one's changes (a diff), and Undo.
function showChanges(el, a, live) {
  const files = a.changes || [];
  const box = el.querySelector(".changes");
  box.hidden = !files.length;
  if (!files.length) return;
  const tilde = (p) => p.replace(/^\/Users\/[^/]+/, "~");
  el.querySelector(".changes-label").textContent =
    `${a.undone ? "Undone: changed" : "Changed"} ${files.length} file${files.length > 1 ? "s" : ""}`;
  el.querySelector(".changes-list").innerHTML = files
    .map((f) => {
      const tags = [f.existed ? "" : "new", f.runnable ? "made runnable" : ""].filter(Boolean).join(", ");
      const head = `**${tilde(f.path)}**${tags ? ` (${tags})` : ""}`;
      return render(f.diff ? `${head}\n\n\`\`\`diff\n${f.diff}\n\`\`\`` : head);
    })
    .join("");
  const undo = el.querySelector(".undo-button");
  undo.hidden = live || !!a.undone;
  el.querySelector(".undo-note").textContent = a.undone ? (a.undo_notes || []).join(" ") || "Put back as they were." : "";
}

thread.addEventListener("click", async (event) => {
  const button = event.target.closest(".undo-button");
  if (!button) return;
  const el = button.closest(".answer-box");
  const note = el.querySelector(".undo-note");
  if (!button.dataset.sure) {
    button.dataset.sure = "1";
    button.textContent = "Yes, put the files back";
    note.textContent = "This puts every file this answer changed back as it was (new files are removed).";
    return;
  }
  button.disabled = true;
  const res = await fetch(`api/history/${conversation}/undo/${el.dataset.index}`, { method: "POST" });
  const data = await res.json();
  button.disabled = false;
  if (!res.ok) {
    note.textContent = data.detail || "That didn't work.";
    return;
  }
  button.hidden = true;
  el.querySelector(".changes-label").textContent = el.querySelector(".changes-label").textContent.replace(/^Changed/, "Undone: changed");
  note.textContent = data.notes.join(" ");
});

function clearThread(text = "Your answer will show up here.") {
  thread.innerHTML = "";
  const p = document.createElement("p");
  p.className = "empty muted";
  p.textContent = text;
  thread.append(p);
}

function showConversationState() {
  newButton.hidden = !conversation;
  // the Ask tab goes back to this conversation (from History or Settings)
  document.querySelector('.tab[data-view="ask"]').href = address(conversation);
  // switching sub-tab keeps the conversation
  document.querySelectorAll("#view-ask [data-subview]").forEach((el) => (el.href = address(conversation, el.dataset.subview)));
  promptLabel.textContent = conversation ? "Ask a follow-up" : "Question";
}

// ---------- asking and following an answer ----------

function setBusy(busy) {
  askButton.disabled = busy;
  askButton.textContent = busy ? "Answering…" : "Ask";
  stopButton.hidden = !busy;
}

async function follow(jobId, el) {
  job = jobId;
  const mine = ++following;
  setBusy(true);
  while (mine === following) {
    let a;
    try {
      const res = await fetch(`api/jobs/${jobId}`);
      if (!res.ok) break;
      a = await res.json();
    } catch {
      await new Promise((r) => setTimeout(r, 2000));
      continue;
    }
    if (mine !== following) return;
    a.model_name = models.find((m) => m.id === a.model)?.name;
    fillAnswer(el, a, true);
    if (!["waiting", "loading", "thinking", "looking", "answering"].includes(a.status)) break;
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
  if (mine !== following) return;
  job = "";
  setBusy(false);
  refreshStatus();
  // the answer is saved now: find its place in the conversation (for Undo) and show it as saved
  const conv = await fetch(`api/history/${conversation}`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  if (conv && mine === following) {
    const index = conv.messages.length - 1;
    el.dataset.index = index;
    if (conv.messages[index]?.role === "assistant") fillAnswer(el, conv.messages[index], false);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = prompt.value.trim();
  promptError.hidden = true;
  if (!text) {
    promptError.textContent = "Type a question first.";
    promptError.hidden = false;
    return;
  }
  askButton.disabled = true;
  let res;
  try {
    res = await fetch("api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: text, model: modelSelect.value, thinking: thinkingField.hidden ? "" : thinkingSelect.value, can_edit: canEdit.checked, conversation }),
    });
  } catch {
    promptError.textContent = "Can't reach the server.";
    promptError.hidden = false;
    askButton.disabled = false;
    return;
  }
  const data = await res.json();
  if (!res.ok) {
    promptError.textContent = data.detail || "That didn't work.";
    promptError.hidden = false;
    askButton.disabled = false;
    return;
  }
  if (!conversation) {
    thread.innerHTML = "";
    title.textContent = text;
  }
  conversation = data.conversation;
  history.replaceState(null, "", address(conversation));
  showConversationState();
  prompt.value = "";
  thread.append(questionEl(text, "you", canEdit.checked));
  const el = answerEl();
  thread.append(el);
  if (matchMedia("(max-width: 799px)").matches) thread.lastElementChild.previousElementSibling.scrollIntoView({ behavior: "smooth" });
  follow(data.job, el);
  refreshStatus();
});

prompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) form.requestSubmit();
});

stopButton.addEventListener("click", async () => {
  if (!job) return;
  stopButton.disabled = true;
  await fetch(`api/queue/${job}`, { method: "DELETE" });
  stopButton.disabled = false;
});

newButton.addEventListener("click", () => {
  location.hash = address("");
});

// ---------- opening a conversation (from History, or a reload) ----------

function setMode(next) {
  if (next === mode) return;
  mode = next;
  document.querySelectorAll("#view-ask [data-subview]").forEach((el) => {
    if (el.dataset.subview === mode) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  showNote();
  showConversationState();
}

// parts: what follows #ask/ in the address: ["advanced", conversation] or [conversation].
export async function showAsk(parts = []) {
  const advanced = parts[0] === "advanced";
  setMode(advanced ? "advanced" : "standard");
  const convId = (advanced ? parts[1] : parts[0]) || "";
  if (convId === conversation) return;
  following++;
  job = "";
  setBusy(false);
  conversation = "";
  title.textContent = "Answer";
  if (!convId) {
    clearThread();
    showConversationState();
    return;
  }
  clearThread("Loading…");
  const res = await fetch(`api/history/${convId}`);
  if (!res.ok) {
    clearThread("That conversation is gone. Ask something new.");
    showConversationState();
    return;
  }
  const conv = await res.json();
  conversation = conv.id;
  title.textContent = conv.title;
  thread.innerHTML = "";
  for (const m of conv.messages) {
    if (m.role === "user") thread.append(questionEl(m.content, m.from, m.can_edit));
    else {
      const el = answerEl();
      el.dataset.index = conv.messages.indexOf(m);
      fillAnswer(el, m, false);
      thread.append(el);
    }
  }
  if (conv.job) {
    const el = answerEl();
    thread.append(el);
    follow(conv.job, el);
  }
  if (models.some((m) => m.id === conv.model)) {
    modelSelect.value = conv.model;
    showNote();
  }
  showConversationState();
}
