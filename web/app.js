// The page only shows things and talks to the server.
// All image work happens on the server (server/generation.py).

const els = {
  form: document.getElementById("make"),
  theme: document.getElementById("theme"),
  themeToggle: document.getElementById("theme-toggle"),
  themeOptions: document.getElementById("theme-options"),
  themeHint: document.getElementById("theme-hint"),
  prompt: document.getElementById("prompt"),
  promptError: document.getElementById("prompt-error"),
  button: document.getElementById("generate"),
  result: document.getElementById("result"),
};

function showNote(title, text) {
  const note = document.createElement("p");
  note.className = "note";
  const strong = document.createElement("strong");
  strong.textContent = title;
  note.append(strong, text);
  els.result.replaceChildren(note);
}

// --- Theme picker: a drop list you can also type into to search. ---

let themes = [];
let chosen = null; // the theme that will be used
let shown = []; // themes in the open list, after searching
let active = -1; // which of `shown` is highlighted

function isOpen() {
  return !els.themeOptions.hidden;
}

function openList(search = "") {
  const q = search.trim().toLowerCase();
  shown = q
    ? themes
        .filter((t) => `${t.name} ${t.hint}`.toLowerCase().includes(q))
        // Names that start with what you typed come first.
        .sort((a, b) => b.name.toLowerCase().startsWith(q) - a.name.toLowerCase().startsWith(q))
    : themes;
  active = q ? (shown.length ? 0 : -1) : shown.indexOf(chosen);

  if (shown.length) {
    els.themeOptions.replaceChildren(
      ...shown.map((t, i) => {
        const li = document.createElement("li");
        li.setAttribute("role", "option");
        li.id = `theme-option-${i}`;
        li.classList.toggle("chosen", t === chosen);
        li.innerHTML = `<span class="name"></span><span class="hint"></span>`;
        li.querySelector(".name").textContent = t.name;
        li.querySelector(".hint").textContent = t.hint;
        li.addEventListener("click", () => choose(t));
        return li;
      })
    );
  } else {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No theme matches that";
    els.themeOptions.replaceChildren(li);
  }

  els.themeOptions.hidden = false;
  els.theme.setAttribute("aria-expanded", "true");
  highlight(active);
}

function closeList() {
  els.themeOptions.hidden = true;
  els.theme.setAttribute("aria-expanded", "false");
  els.theme.removeAttribute("aria-activedescendant");
}

function highlight(i) {
  active = i;
  [...els.themeOptions.children].forEach((li, n) => li.setAttribute("aria-selected", n === i));
  if (i >= 0) {
    els.theme.setAttribute("aria-activedescendant", `theme-option-${i}`);
    els.themeOptions.children[i].scrollIntoView({ block: "nearest" });
  } else {
    els.theme.removeAttribute("aria-activedescendant");
  }
}

function choose(theme) {
  chosen = theme;
  els.theme.value = theme.name;
  els.themeHint.textContent = theme.hint;
  closeList();
}

els.theme.addEventListener("focus", () => {
  els.theme.select(); // typing replaces the old name
  openList();
});

els.theme.addEventListener("input", () => openList(els.theme.value));

els.theme.addEventListener("blur", () => {
  closeList();
  if (chosen) els.theme.value = chosen.name; // half-typed text goes back to the chosen theme
});

els.theme.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    if (!isOpen()) return openList();
    if (!shown.length) return;
    const step = e.key === "ArrowDown" ? 1 : -1;
    highlight((active + step + shown.length) % shown.length);
  } else if (e.key === "Enter") {
    e.preventDefault(); // don't press Generate from the theme box
    if (isOpen() && active >= 0) choose(shown[active]);
  } else if (e.key === "Escape" && isOpen()) {
    closeList();
    if (chosen) els.theme.value = chosen.name;
  }
});

// Tapping the list or the arrow must not take focus away from the text box,
// or the list would close before the tap lands.
for (const el of [els.themeOptions, els.themeToggle]) {
  el.addEventListener("mousedown", (e) => e.preventDefault());
}

els.themeToggle.addEventListener("click", () => {
  if (isOpen()) closeList();
  else if (document.activeElement === els.theme) openList();
  else els.theme.focus();
});

async function loadThemes() {
  try {
    const res = await fetch("api/themes");
    themes = await res.json();
    els.theme.disabled = false;
    els.theme.placeholder = "Pick or type a theme";
    if (themes.length) choose(themes[0]);
  } catch {
    els.theme.placeholder = "Couldn't load themes";
    els.themeHint.textContent = "Is the server running?";
  }
}

// --- Generate ---

async function onGenerate(event) {
  event.preventDefault();
  const theme = chosen?.id;
  const prompt = els.prompt.value.trim();

  if (!theme) return showNote("Pick a theme first", "");
  // Shown right under the box (not in the result area, which the phone
  // keyboard can hide).
  els.promptError.hidden = Boolean(prompt);
  if (!prompt) return;

  // Close the phone keyboard and bring the result area into view.
  document.activeElement?.blur();
  els.button.disabled = true;
  els.button.textContent = "Working…";
  showSpinner();
  els.result.scrollIntoView({ behavior: "smooth", block: "center" });
  try {
    const res = await fetch("api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme, prompt }),
    });
    const data = await res.json();
    if (data.status === "done") {
      showImage(data.image);
    } else {
      showNote("Something unexpected came back", JSON.stringify(data));
    }
  } catch {
    showNote("Couldn't reach the server", "Check that it's still running.");
  } finally {
    els.button.disabled = false;
    els.button.textContent = "Generate";
  }
}

function showSpinner() {
  const box = document.createElement("div");
  box.className = "working";
  box.innerHTML = `<div class="spinner" aria-hidden="true"></div><p>Making your picture…</p>`;
  els.result.replaceChildren(box);
}

function showImage(url) {
  const img = document.createElement("img");
  img.className = "picture";
  img.alt = "Your picture";
  img.src = url;

  const save = document.createElement("a");
  save.className = "button";
  save.href = `${url}?download=1`;
  save.download = "";
  save.textContent = "Download";

  const box = document.createElement("div");
  box.className = "done";
  box.append(img, save);
  els.result.replaceChildren(box);
}

els.form.addEventListener("submit", onGenerate);
els.prompt.addEventListener("input", () => (els.promptError.hidden = true));
loadThemes();
