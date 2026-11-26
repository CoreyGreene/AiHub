const $ = (id) => document.getElementById(id);
const form = $("generate-form");
const promptField = $("prompt");
const model = $("model");
const seconds = $("seconds");
const generate = $("generate");
const search = $("search");
const clipTemplate = $("clip-template");
const deleteRecent = $("delete-recent");
const recentConfirm = $("recent-confirm");
const recentStatus = $("recent-status");
let clips = [];
let modelReady = false;
let pending = false;
let seenJob = "";
let timer;

async function api(path, options) {
  const response = await fetch(`api/${path}`, { cache: "no-store", ...options });
  if (response.status === 204) return;
  let data;
  try { data = await response.json(); } catch { /* The hub may be starting the tool. */ }
  if (!response.ok) {
    throw new Error(typeof data?.detail === "string" ? data.detail : "Couldn't reach Sound AI.");
  }
  return data;
}

function send(path, method, body) {
  return api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

function notice(message = "") {
  $("notice").hidden = !message;
  $("notice").textContent = message;
}

function view() {
  const library = location.hash === "#library";
  $("create").hidden = library;
  $("library").hidden = !library;
  $("create-tab").removeAttribute("aria-current");
  $("library-tab").removeAttribute("aria-current");
  $(library ? "library-tab" : "create-tab").setAttribute("aria-current", "page");
}

function showCards(target, items, emptyText) {
  if (items.length) {
    target.replaceChildren(...items.map(card));
  } else {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = emptyText;
    target.replaceChildren(empty);
  }
}

function renderLibrary() {
  const saved = clips.filter((clip) => clip.saved);
  const query = search.value.trim().toLowerCase();
  $("library-count").textContent = saved.length || "";
  showCards($("saved"), saved.filter((clip) => `${clip.name} ${clip.prompt}`.toLowerCase().includes(query)),
    query ? "No saved sounds match." : "Save a sound from Create and it’ll appear here.");
}

function render() {
  const recent = clips.filter((clip) => !clip.saved);
  deleteRecent.hidden = !recent.length;
  if (!recent.length) recentConfirm.hidden = true;
  showCards($("recent"), recent, "New sounds will appear here.");
  renderLibrary();
}

function card(clip) {
  const node = clipTemplate.content.firstElementChild.cloneNode(true);
  const soundPath = `sounds/${clip.id}`;
  const status = node.querySelector(".clip-status");
  const setStatus = (text) => {
    status.hidden = !text;
    status.textContent = text;
  };
  node.querySelector("h3").textContent = clip.name || "New sound";
  node.querySelector(".length").textContent = `${clip.seconds} sec`;
  node.querySelector(".clip-prompt").textContent = clip.prompt;
  const audio = node.querySelector("audio");
  audio.src = `api/${soundPath}/audio`;
  audio.setAttribute("aria-label", `Play ${clip.name || clip.prompt}`);
  audio.addEventListener("play", () => {
    document.querySelectorAll("audio").forEach((player) => { if (player !== audio) player.pause(); });
  });
  node.querySelector(".download").href = `api/${soundPath}/audio?download=true`;
  node.querySelector(".reuse").addEventListener("click", () => {
    promptField.value = clip.prompt;
    seconds.value = clip.seconds;
    location.hash = "create";
    view();
    promptField.focus();
  });

  const save = node.querySelector(".save-form");
  save.hidden = clip.saved;
  save.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = save.querySelector("button");
    button.disabled = true;
    try {
      const updated = await send(soundPath, "PUT", { name: save.querySelector("input").value });
      const index = clips.findIndex((item) => item.id === clip.id);
      if (index >= 0) clips[index] = updated;
      render();
      notice(`Saved “${updated.name}” to the Library.`);
    } catch (error) {
      setStatus(error.message);
      button.disabled = false;
    }
  });

  const remove = node.querySelector(".remove");
  remove.addEventListener("click", async () => {
    if (remove.textContent === "Delete") {
      remove.textContent = "Confirm delete";
      setStatus("Tap again to delete this sound.");
      return;
    }
    remove.disabled = true;
    try {
      await api(soundPath, { method: "DELETE" });
      clips = clips.filter((item) => item.id !== clip.id);
      render();
    } catch (error) {
      setStatus(error.message);
      remove.disabled = false;
    }
  });
  return node;
}

function showJob(job) {
  const working = job?.state === "working";
  generate.disabled = !modelReady || working || pending;
  $("job").hidden = !job;
  if (!job) return;
  $("job-status").textContent = working && job.step > 0 && job.stage === "Generating" ?
    `${job.stage} · ${job.step} of ${job.steps}` : job.stage;
  const progress = $("progress");
  progress.hidden = !working;
  progress.max = job.steps;
  if (job.step) progress.value = job.step;
  else progress.removeAttribute("value");
}

async function refresh() {
  try {
    const status = await api("status");
    if (model.value !== status.model.id) {
      model.replaceChildren(new Option(status.model.name, status.model.id));
    }
    modelReady = status.model_ready;
    showJob(status.job);
    if (!modelReady) notice("Stable Audio 3 Small SFX is missing in SoundModels.");
    if (status.job?.state === "done" && status.job.id !== seenJob) {
      clips = await api("sounds");
      seenJob = status.job.id;
      render();
    }
  } catch (error) {
    generate.disabled = true;
    notice(error.message);
  } finally {
    timer = setTimeout(refresh, 1250);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (pending || generate.disabled) return;
  pending = true;
  generate.disabled = true;
  notice();
  try {
    showJob(await send("generate", "POST", {
      prompt: promptField.value, seconds: seconds.valueAsNumber, model: model.value,
    }));
  } catch (error) {
    notice(error.message);
    generate.disabled = !modelReady;
  } finally {
    pending = false;
  }
});

deleteRecent.addEventListener("click", () => {
  recentConfirm.hidden = false;
  recentStatus.hidden = true;
  $("cancel-delete-recent").focus();
});
$("cancel-delete-recent").addEventListener("click", () => {
  recentConfirm.hidden = true;
  deleteRecent.focus();
});
$("confirm-delete-recent").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const { removed } = await api("recent", { method: "DELETE" });
    const ids = new Set(removed);
    clips = clips.filter((clip) => !ids.has(clip.id));
    recentConfirm.hidden = true;
    recentStatus.textContent = removed.length === 1 ? "Deleted 1 unsaved sound." :
      `Deleted ${removed.length} unsaved sounds.`;
    render();
  } catch (error) {
    recentStatus.textContent = error.message;
  } finally {
    recentStatus.hidden = false;
    button.disabled = false;
  }
});

$("create-tab").addEventListener("click", () => { location.hash = "create"; });
$("library-tab").addEventListener("click", () => { location.hash = "library"; });
window.addEventListener("hashchange", () => { notice(); recentConfirm.hidden = true; view(); });
window.addEventListener("pagehide", () => clearTimeout(timer));
window.addEventListener("pageshow", ({ persisted }) => { if (persisted) refresh(); });
search.addEventListener("input", renderLibrary);
view();
try {
  clips = await api("sounds");
  render();
} catch (error) {
  notice(error.message);
}
refresh();
