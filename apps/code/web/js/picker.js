// A folder (or file) picker over the folders CodeAi may look in, walked on the server, so it works from the phone
// too and gives a real path on this Mac. pick({mode: "folder" | "json", start}) -> the chosen path, or null.

const $ = (id) => document.getElementById(id);
const dialog = $("picker");
const list = $("picker-list");
const tilde = (p) => (p || "").replace(/^\/Users\/[^/]+/, "~");

let current = null; // what the server said about the folder shown
let mode = "folder";
let finish = () => {};

function showError(text) {
  $("picker-error").textContent = text;
  $("picker-error").hidden = !text;
}

function row(label, kind, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = `picker-row is-${kind}`;
  b.textContent = label;
  b.addEventListener("click", onClick);
  return b;
}

async function open(path) {
  showError("");
  const ext = mode === "json" ? "&ext=.json" : "";
  const res = await fetch(`api/browse?path=${encodeURIComponent(path || "")}${ext}`).catch(() => null);
  if (!res?.ok) {
    if (path) return open(""); // a remembered folder that's gone: start at the top
    return showError(res ? (await res.json()).detail : "Can't reach CodeAi.");
  }
  current = await res.json();
  $("picker-path").textContent = current.path ? tilde(current.path) : current.name;
  $("picker-up").disabled = current.up === null;
  $("picker-use").hidden = mode !== "folder" || !current.path;
  list.innerHTML = "";
  for (const f of current.folders) list.append(row(f.name, "folder", () => open(f.path)));
  for (const f of current.files) list.append(row(f.name, "file", () => done(f.path)));
  if (!list.children.length)
    list.innerHTML = `<p class="muted small">${mode === "json" ? "No folders or .json files here." : "No folders inside this one."}</p>`;
}

function done(path) {
  if (path && current?.path) localStorage.setItem(`codeai-picker-${mode}`, current.path);
  dialog.close();
  finish(path);
}

$("picker-up").addEventListener("click", () => current && current.up !== null && open(current.up));
$("picker-use").addEventListener("click", () => done(current.path));
$("picker-close").addEventListener("click", () => done(null));
dialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  done(null);
});

export function pick({ mode: m = "folder", start = "", title = "" } = {}) {
  mode = m;
  $("picker-title").textContent = title || (mode === "json" ? "Open a bulk file" : "Choose the folder it works in");
  dialog.showModal();
  open(start || localStorage.getItem(`codeai-picker-${mode}`) || "");
  return new Promise((resolve) => (finish = resolve));
}
