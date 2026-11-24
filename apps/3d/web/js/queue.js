// Queue: the job being made, then the waiting ones, then the finished ones.

import { api, el, jobLine } from "./api.js";

const list = document.getElementById("queue-list");
let timer = null;

export function showQueue() {
  load();
}

async function load() {
  clearTimeout(timer);
  if (document.getElementById("view-queue").hidden) return;
  try {
    const jobs = await api("api/jobs");
    const active = jobs.filter((j) => j.status === "working" || j.status === "waiting")
      .sort((a, b) => (a.status === "working" ? -1 : b.status === "working" ? 1 : 0));
    const finished = jobs.filter((j) => !active.includes(j)).reverse().slice(0, 50);
    const parts = [];
    if (!jobs.length) parts.push(el("p", "muted", "Nothing yet."));
    if (active.length) parts.push(el("p", "job-group", "Now and next"), ...active.map(row));
    if (finished.length) parts.push(el("p", "job-group", "Finished"), ...finished.map(row));
    list.replaceChildren(...parts);
  } catch (err) {
    list.replaceChildren(el("p", "muted", err.message));
  }
  timer = setTimeout(load, 2500);
}

function row(job) {
  const div = el("div", `job ${job.status}`);
  const name = el("a", "", job.name);
  name.href = `#library/${encodeURIComponent(job.slug)}`;
  div.append(el("strong"), el("span", "muted small", jobLine(job)));
  div.firstChild.append(name);
  if (job.status === "waiting" || job.status === "working") {
    const b = el("button", "button small-button", job.status === "working" ? "Stop" : "Remove");
    b.type = "button";
    b.addEventListener("click", async () => {
      b.disabled = true;
      await api(`api/jobs/${job.id}/stop`, { method: "POST" }).catch(() => {});
      load();
    });
    div.append(b);
  }
  return div;
}
