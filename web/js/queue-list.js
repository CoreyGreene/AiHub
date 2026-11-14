// The video queue on the Settings page: every job being made or waiting,
// in order, each with a Remove button (tap twice: the first tap asks).
// Refreshed every couple of seconds while the Settings page is open.

const list = document.getElementById("queue-list");
const view = document.getElementById("view-settings");
const REFRESH_MS = 2000;
const CONFIRM_MS = 4000;

let timer = null;
let asking = null; // id of the job whose Remove is waiting for a second tap

export function startQueueList() {
  refresh();
  if (!timer) timer = setInterval(refresh, REFRESH_MS);
}

async function refresh() {
  if (view.hidden || document.hidden) {
    clearInterval(timer);
    timer = null;
    return;
  }
  try {
    const res = await fetch("api/queue");
    const jobs = await res.json();
    if (!jobs.length) {
      list.innerHTML = `<li class="muted queue-empty">Nothing in the queue.</li>`;
      return;
    }
    list.replaceChildren(...jobs.map(row));
  } catch {
    list.innerHTML = `<li class="muted queue-empty">Couldn't load the queue. Is the server running?</li>`;
  }
}

function describe(job) {
  const videos = `${job.count} video${job.count > 1 ? "s" : ""}`;
  if (job.stopping) return `Stopping… · ${videos}`;
  if (job.status === "waiting") return `Waiting · ${videos}`;
  const which = job.count > 1 ? `video ${job.number} of ${job.count}` : "making";
  const step = job.steps ? ` · step ${job.step} of ${job.steps}` : "";
  return `Making · ${which}${step}`;
}

function row(job) {
  const li = document.createElement("li");
  li.className = `queue-item ${job.status}`;
  li.innerHTML = `
    <div class="queue-info">
      <span class="queue-state"></span>
      <span class="queue-prompt"></span>
      <span class="muted small queue-theme"></span>
    </div>
    <button type="button" class="button queue-remove"></button>`;
  li.querySelector(".queue-state").textContent = describe(job);
  li.querySelector(".queue-prompt").textContent = job.prompt;
  li.querySelector(".queue-theme").textContent = job.theme;

  const remove = li.querySelector(".queue-remove");
  const verb = job.status === "working" ? "Stop" : "Remove";
  remove.textContent = asking === job.id ? `${verb}? Tap again` : verb;
  remove.classList.toggle("asking", asking === job.id);
  remove.disabled = job.stopping;
  remove.addEventListener("click", () => onRemove(job.id));
  return li;
}

async function onRemove(id) {
  if (asking !== id) {
    asking = id; // first tap: ask
    refresh();
    setTimeout(() => {
      if (asking === id) {
        asking = null;
        refresh();
      }
    }, CONFIRM_MS);
    return;
  }
  asking = null;
  await fetch(`api/queue/${id}`, { method: "DELETE" }).catch(() => {});
  refresh();
}
