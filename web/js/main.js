// The tabs (#make, #library[/<model>], #bulk, #queue) and the status line.

import { api } from "./api.js";
import { showMake } from "./make.js";
import { showLibrary } from "./library.js";
import { showBulk } from "./bulk.js";
import { showQueue } from "./queue.js";

const views = { make: showMake, library: showLibrary, bulk: showBulk, queue: showQueue };

function route() {
  const [view, ...rest] = (location.hash.slice(1) || "make").split("/");
  const name = views[view] ? view : "make";
  for (const main of document.querySelectorAll("main.view")) main.hidden = main.id !== `view-${name}`;
  for (const tab of document.querySelectorAll(".tab")) {
    if (tab.dataset.view === name) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
  views[name](...rest.map(decodeURIComponent));
}
window.addEventListener("hashchange", route);
route();

// Status: is TRELLIS ready, loaded, busy; how many jobs wait.
const status = document.getElementById("status");
const problem = document.getElementById("problem");
const queueCount = document.getElementById("queue-count");
async function checkStatus() {
  try {
    const s = await api("api/status");
    problem.hidden = !s.problem;
    problem.textContent = s.problem;
    const busy = Boolean(s.working);
    status.classList.toggle("busy", busy);
    status.textContent = busy
      ? `Making ${s.working}${s.waiting ? ` · ${s.waiting} waiting` : ""}`
      : s.loaded ? "TRELLIS ready" : "Idle";
    const active = s.waiting + (busy ? 1 : 0);
    queueCount.hidden = !active;
    queueCount.textContent = active;
  } catch {
    status.textContent = "Not connected";
  }
}
checkStatus();
setInterval(checkStatus, 3000);
