// The line at the top: which graphics card, how much of its memory is used
// (whole card) and taken by this website, and the video queue. Refreshed
// every few seconds while the page is on screen.

const box = document.getElementById("gpu");
const REFRESH_MS = 3000;

const gb = (n) => `${n.toFixed(1)} GB`;

function queueText({ working, waiting }) {
  if (!working && !waiting) return "Queue: empty";
  return `Queue: ${working ? "1 making" : "0 making"} · ${waiting} waiting`;
}

async function refresh() {
  if (document.hidden) return;
  try {
    const res = await fetch("api/status");
    const { gpu: g, queue } = await res.json();
    box.innerHTML = `
      <span class="gpu-name"></span>
      <span class="gpu-meter" aria-hidden="true"><span class="used"></span><span class="mine"></span></span>
      <span class="gpu-text"></span>
      <span class="gpu-queue"></span>`;
    box.querySelector(".gpu-name").textContent = g.name;
    const queueBox = box.querySelector(".gpu-queue");
    queueBox.textContent = queueText(queue);
    queueBox.classList.toggle("busy", queue.working + queue.waiting > 0);
    if (g.total_gb === undefined) {
      box.querySelector(".gpu-meter").remove();
      box.querySelector(".gpu-text").remove();
      return;
    }
    box.querySelector(".used").style.width = `${(g.used_gb / g.total_gb) * 100}%`;
    box.querySelector(".mine").style.width = `${(g.allocated_gb / g.total_gb) * 100}%`;
    box.querySelector(".gpu-text").textContent =
      `${gb(g.used_gb)} of ${gb(g.total_gb)} used · this site ${gb(g.allocated_gb)}`;
  } catch {
    box.textContent = "Graphics card: can't reach the server";
  }
}

export function startGpu() {
  refresh();
  setInterval(refresh, REFRESH_MS);
  document.addEventListener("visibilitychange", refresh);
}
