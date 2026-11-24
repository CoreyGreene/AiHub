// Small helpers shared by every tab.

// fetch JSON; a server "detail" becomes the error message.
export async function api(url, options = {}) {
  let res;
  try {
    res = await fetch(url, options);
  } catch {
    throw new Error("Couldn't reach MeshAi. Is it still running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Something went wrong (${res.status}).`);
  return data;
}

export const postJson = (url, body) =>
  api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

export function showError(line, err) {
  line.textContent = err ? err.message || String(err) : "";
  line.hidden = !err;
}

// What a job is doing, in plain words.
const STAGES = {
  loading: "Loading TRELLIS (about a minute, first job only)",
  shape: "Making the shape",
  texture: "Painting the texture",
  saving: "Saving",
};
export function jobLine(job) {
  if (job.status === "waiting") return "Waiting";
  if (job.status === "working") return `${STAGES[job.stage] || "Starting"}… ${job.running ? `${job.running} s` : ""}`.trim();
  if (job.status === "done") return `Done in ${Math.round(job.seconds)} s`;
  if (job.status === "stopped") return job.message || "Stopped";
  return job.message || "Failed";
}

// A button that asks once more before doing something that can't be undone.
export function askFirst(button, question, action) {
  const original = button.textContent;
  let timer = null;
  button.addEventListener("click", async () => {
    if (!button.classList.contains("asking")) {
      button.classList.add("asking");
      button.textContent = question;
      timer = setTimeout(() => {
        button.classList.remove("asking");
        button.textContent = original;
      }, 4000);
      return;
    }
    clearTimeout(timer);
    button.classList.remove("asking");
    button.textContent = original;
    await action();
  });
}

export const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
