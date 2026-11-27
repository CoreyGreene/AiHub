// One on-disk text file. A draft stays in this page until Save is pressed.

import { pick } from "./picker.js";
import { lineAuthors } from "./editor-lines.js";

const $ = (id) => document.getElementById(id);
const panel = $("editor-panel");
const input = $("editor-text");
const highlights = $("editor-highlights");
const save = $("editor-save");
const discard = $("editor-discard");
const close = $("editor-close");
const open = $("editor-open");
const chat = $("ask-chat");
const chatToggle = $("editor-chat-toggle");
let file = null;
let baseline = "";
let savedAuthors = [];
let visibleAuthors = savedAuthors;
let request = 0;
let refreshing = null;
let asking = false;
let opening = false;
let saving = false;
let conflict = false;
let available = false;
let armed = false;

const dirty = () => file && input.value !== baseline;

function paintHighlights() {
  if (panel.hidden || !input.clientHeight) return;
  const style = getComputedStyle(input);
  const height = parseFloat(style.lineHeight);
  const top = parseFloat(style.paddingTop) - input.scrollTop;
  const first = Math.max(0, Math.floor(-top / height));
  const last = Math.min(visibleAuthors.length, Math.ceil((input.clientHeight - top) / height));
  const rows = [];
  for (let line = first; line < last; line++) {
    const author = visibleAuthors[line];
    if (!author) continue;
    const row = document.createElement("span");
    row.className = `editor-${author}`;
    row.style.top = `${top + line * height}px`;
    row.style.height = `${height}px`;
    rows.push(row);
  }
  highlights.replaceChildren(...rows);
}

function message(text) {
  $("editor-message").textContent = text;
  $("editor-message").hidden = !text;
}

function render() {
  const locked = asking || file?.busy || opening || saving || !available || conflict;
  input.readOnly = Boolean(locked);
  save.disabled = Boolean(locked) || !dirty();
  close.disabled = saving || opening;
  discard.hidden = !dirty();
  discard.disabled = saving || opening;
  $("editor-state").textContent = conflict ? "The file changed on disk. Your draft is still here." :
    asking || file?.busy ? "Code AI is working. Read-only for now." :
      !available ? "Waiting for the file…" : saving ? "Saving…" :
        dirty() ? "Unsaved changes" : "Ready to edit";
  discard.textContent = armed ? "Confirm discard" : "Discard draft";
}

async function api(path, revision = "") {
  const params = new URLSearchParams({ path, revision });
  const res = await fetch(`api/editor?${params}`, { cache: "no-store" });
  const data = await res.json();
  if (!res.ok) throw Error(data.detail);
  return data;
}

function accept(data, author = data.author) {
  const sameFile = file?.path === data.path;
  file = data;
  if ("text" in data) {
    const text = data.text.replace(/\r\n?/g, "\n");
    if (sameFile && baseline !== text) {
      savedAuthors = lineAuthors(baseline, savedAuthors, text, ["you", "ai"].includes(author) ? author : "");
    } else if (!sameFile) {
      savedAuthors = [];
    }
    if (!sameFile || input.value !== text) {
      const top = sameFile ? input.scrollTop : 0;
      const left = sameFile ? input.scrollLeft : 0;
      input.value = text;
      input.scrollTop = top;
      input.scrollLeft = left;
    }
    baseline = text;
    visibleAuthors = savedAuthors;
  }
  $("editor-path").textContent = data.path.replace(/^\/Users\/[^/]+/, "~");
  available = true;
  conflict = false;
  armed = false;
  panel.hidden = false;
  render();
  paintHighlights();
}

async function refresh(force = false) {
  if (!file || saving || opening || (refreshing && !force)) return;
  const mine = ++request;
  refreshing = mine;
  try {
    const data = await api(file.path, force ? "" : file.revision);
    if (mine !== request) return;
    if (!force && data.revision !== file.revision && dirty()) {
      conflict = true;
      file.busy = data.busy;
      available = true;
      render();
    } else if ("text" in data) {
      if (!force) message("Updated from disk.");
      accept(data);
    } else {
      file.busy = data.busy;
      available = true;
      conflict = false;
      render();
    }
  } catch (error) {
    if (mine !== request) return;
    available = false;
    message(error.message || "Couldn't refresh the file.");
    render();
  } finally {
    if (refreshing === mine) refreshing = null;
  }
}

export async function openEditor(path) {
  if (!path || path === file?.path || dirty() || saving) return;
  const mine = ++request;
  opening = true;
  render();
  $("editor-open-error").hidden = true;
  try {
    const data = await api(path);
    if (mine !== request) return;
    message("");
    accept(data);
    if (matchMedia("(max-width: 799px)").matches) {
      panel.scrollIntoView({ block: "start" });
    }
  } catch (error) {
    if (mine !== request) return;
    $("editor-open-error").textContent = error.message || "Couldn't open that file.";
    $("editor-open-error").hidden = false;
  } finally {
    if (mine === request) {
      opening = false;
      render();
    }
  }
}

export function setEditorBusy(value) {
  asking = value;
  if (!value && file) {
    available = false;
    refresh();
  }
  render();
}

export function editorPath(folder) {
  const root = folder.replace(/\/$/, "");
  return file && (!root || file.path.startsWith(`${root}/`)) ? file.path : "";
}

export function editorHasDraft() {
  return Boolean(dirty() || saving);
}

export function connectEditor(workFolder) {
  open.addEventListener("click", async () => {
    if (editorHasDraft()) {
      $("editor-open-error").textContent = "Save or discard your draft before opening another file.";
      $("editor-open-error").hidden = false;
      return;
    }
    const folder = workFolder();
    const path = await pick({ mode: "text", start: folder, boundary: folder, title: "Open a text file" });
    if (path) openEditor(path);
  });
}

input.addEventListener("input", () => {
  armed = false;
  visibleAuthors = dirty() ? lineAuthors(baseline, savedAuthors, input.value, "you") : savedAuthors;
  message("");
  render();
  paintHighlights();
});
input.addEventListener("scroll", paintHighlights);
new ResizeObserver(paintHighlights).observe(input);

function setChatVisible(visible) {
  chat.hidden = !visible;
  chatToggle.setAttribute("aria-expanded", String(visible));
  chatToggle.textContent = visible ? "Hide chat" : "Show chat";
}

chatToggle.addEventListener("click", () => setChatVisible(chat.hidden));

close.addEventListener("click", () => {
  if (dirty()) return message("Save or discard your draft before closing.");
  request++;
  file = null;
  panel.hidden = true;
  setChatVisible(true);
  message("");
  open.focus();
});

discard.addEventListener("click", async () => {
  if (!armed) {
    armed = true;
    message("Tap again to discard your unsaved edits.");
    render();
    return;
  }
  message("");
  await refresh(true);
});

save.addEventListener("click", async () => {
  if (save.disabled) return;
  saving = true;
  request++;
  render();
  try {
    const response = await fetch("api/editor", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: file.path, text: input.value, revision: file.revision }),
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.detail);
    accept(data, "you");
    message(data.syntax_error ? `Saved. Syntax check found: ${data.syntax_error}` : "Saved to disk.");
  } catch (error) {
    message(error.message || "Couldn't save the file.");
  } finally {
    saving = false;
    render();
    refresh();
  }
});

setInterval(() => {
  if (!document.hidden && !$("view-ask").hidden) refresh();
}, 1000);
