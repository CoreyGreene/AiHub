// The History tab: every past conversation, newest first. Open carries it on in Ask; Delete asks first (in the
// page, no pop-ups).

const list = document.getElementById("history-list");

function when(seconds) {
  return new Date(seconds * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function row(c, names) {
  const el = document.createElement("div");
  el.className = "history-row";
  el.innerHTML = `
    <a class="history-open"><strong></strong><span></span></a>
    <div class="history-actions"><button type="button" class="button small-button danger">Delete</button></div>`;
  const open = el.querySelector(".history-open");
  open.href = `#ask/${c.id}`;
  open.querySelector("strong").textContent = c.title;
  const questions = `${c.questions} question${c.questions === 1 ? "" : "s"}`;
  open.querySelector("span").textContent = `${names[c.model] || c.model} · ${questions} · ${when(c.updated)}`;
  el.querySelector(".danger").addEventListener("click", () => askToDelete(el, c));
  return el;
}

function askToDelete(el, c) {
  if (el.querySelector(".history-ask")) return;
  const box = document.createElement("div");
  box.className = "history-ask";
  box.innerHTML = `<p>Delete this conversation for good?</p>
    <button type="button" class="button small-button danger">Yes, delete</button>
    <button type="button" class="button small-button">Keep it</button>
    <span class="error-line" hidden></span>`;
  const [yes, no] = box.querySelectorAll("button");
  no.addEventListener("click", () => box.remove());
  yes.addEventListener("click", async () => {
    yes.disabled = true;
    const res = await fetch(`api/history/${c.id}`, { method: "DELETE" });
    if (res.ok) {
      el.remove();
      if (!list.children.length) list.innerHTML = `<p class="muted">No conversations yet.</p>`;
      return;
    }
    const error = box.querySelector(".error-line");
    error.textContent = (await res.json()).detail || "That didn't work.";
    error.hidden = false;
    yes.disabled = false;
  });
  el.append(box);
}

export async function loadHistory() {
  try {
    const [convs, models] = await Promise.all([
      fetch("api/history").then((r) => r.json()),
      fetch("api/models").then((r) => r.json()),
    ]);
    const names = Object.fromEntries(models.models.map((m) => [m.id, m.name]));
    list.innerHTML = "";
    if (!convs.length) list.innerHTML = `<p class="muted">No conversations yet.</p>`;
    for (const c of convs) list.append(row(c, names));
  } catch {
    list.innerHTML = `<p class="muted">Can't reach the server.</p>`;
  }
}
