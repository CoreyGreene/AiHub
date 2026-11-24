// Settings (the gear): which model is in memory, a button to let it go, and the queue with a Stop for each.

import { onStatus, refreshStatus } from "./status.js";

const state = document.getElementById("model-state");
const unloadButton = document.getElementById("unload-button");
const unloadError = document.getElementById("unload-error");
const queueList = document.getElementById("queue-list");
let timer = 0;

onStatus(({ model }) => {
  if (!model.id) state.textContent = "No model is loaded. The next question loads one.";
  else if (model.state === "loading") state.textContent = `Loading ${model.name}…`;
  else state.textContent = `${model.name} is loaded. It's let go after a while with no questions.`;
  unloadButton.hidden = !model.id || model.state === "loading";
});

unloadButton.addEventListener("click", async () => {
  unloadError.hidden = true;
  unloadButton.disabled = true;
  const res = await fetch("api/model/unload", { method: "POST" });
  if (!res.ok) {
    unloadError.textContent = (await res.json()).detail || "That didn't work.";
    unloadError.hidden = false;
  }
  unloadButton.disabled = false;
  refreshStatus();
});

const what = { waiting: "Waiting", loading: "Loading the model", thinking: "Thinking", looking: "Looking at files", answering: "Answering" };

async function showQueue() {
  if (location.hash !== "#settings") return clearInterval(timer);
  const jobs = await fetch("api/queue").then((r) => r.json()).catch(() => null);
  if (!jobs) return;
  queueList.innerHTML = "";
  if (!jobs.length) queueList.innerHTML = `<p class="muted">Nothing waiting.</p>`;
  for (const j of jobs) {
    const el = document.createElement("div");
    el.className = "queue-row";
    el.innerHTML = `<p><strong></strong><br><span class="muted small"></span></p>
      <button type="button" class="button small-button danger">Stop</button>`;
    el.querySelector("strong").textContent = j.prompt.length > 120 ? j.prompt.slice(0, 117) + "…" : j.prompt;
    el.querySelector(".muted").textContent =
      `${j.stopping ? "Stopping" : what[j.status]} · ${j.model} · asked by ${j.source === "claude" ? "Claude" : "you"}`;
    el.querySelector("button").addEventListener("click", async (e) => {
      e.target.disabled = true;
      await fetch(`api/queue/${j.id}`, { method: "DELETE" });
      showQueue();
    });
    queueList.append(el);
  }
}

export function loadSettings() {
  refreshStatus();
  showQueue();
  clearInterval(timer);
  timer = setInterval(showQueue, 2000);
}
