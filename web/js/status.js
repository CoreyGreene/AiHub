// The line at the top: the GPU's memory (whole Mac / taken by the model), which model is loaded, and the queue.
// Refreshed every few seconds while the page is on screen. Others can ask for the latest with lastStatus().

const box = document.getElementById("status");
const REFRESH_MS = 3000;
let latest = null;
const listeners = [];

const gb = (n) => `${n.toFixed(1)} GB`;

function queueText({ working, waiting }) {
  if (!working && !waiting) return "Queue: empty";
  return `Queue: ${working ? "1 answering" : "0 answering"} · ${waiting} waiting`;
}

function modelText(model) {
  if (!model.id) return "No model loaded";
  return model.state === "loading" ? `Loading ${model.name}…` : model.name;
}

async function refresh() {
  if (document.hidden) return;
  try {
    const res = await fetch("api/status");
    latest = await res.json();
    const { memory: m, model, queue } = latest;
    box.innerHTML = `
      <span class="gpu-name"></span>
      <span class="gpu-meter" aria-hidden="true"><span class="used"></span><span class="mine"></span></span>
      <span class="gpu-text"></span>
      <span class="gpu-queue"></span>`;
    box.querySelector(".gpu-name").textContent = modelText(model);
    const queueBox = box.querySelector(".gpu-queue");
    queueBox.textContent = queueText(queue);
    queueBox.classList.toggle("busy", queue.working + queue.waiting > 0);
    if (!m.total_gb) {
      box.querySelector(".gpu-meter").remove();
      box.querySelector(".gpu-text").textContent = m.name;
    } else {
      box.querySelector(".used").style.width = `${Math.min(m.used_gb / m.total_gb, 1) * 100}%`;
      box.querySelector(".mine").style.width = `${Math.min(m.mine_gb / m.total_gb, 1) * 100}%`;
      box.querySelector(".gpu-text").textContent = `${gb(m.used_gb)} of ${gb(m.total_gb)} used · model ${gb(m.mine_gb)}`;
    }
    listeners.forEach((fn) => fn(latest));
  } catch {
    box.textContent = "Can't reach the server";
  }
}

export const lastStatus = () => latest;
export const onStatus = (fn) => listeners.push(fn);
export const refreshStatus = refresh;

export function startStatus() {
  refresh();
  setInterval(refresh, REFRESH_MS);
  document.addEventListener("visibilitychange", refresh);
}
