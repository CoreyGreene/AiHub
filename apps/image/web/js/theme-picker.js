// Theme picker: a drop list you can also type into to search.

const input = document.getElementById("theme-name");
const toggle = document.getElementById("theme-toggle");
const options = document.getElementById("theme-options");
const hint = document.getElementById("theme-hint");

let themes = [];
let chosen = null; // the theme that will be used
let shown = []; // themes in the open list, after searching
let active = -1; // which of `shown` is highlighted

let onChange = () => {};

export function chosenTheme() {
  return chosen;
}

// Call fn(theme) whenever a different theme is picked.
export function whenThemeChanges(fn) {
  onChange = fn;
}

// Choose a theme by its id (a workflow item being changed).
export function pickTheme(id) {
  const theme = themes.find((t) => t.id === id);
  if (theme) choose(theme);
}

export function resetTheme() {
  if (themes.length) choose(themes[0]);
}

function isOpen() {
  return !options.hidden;
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
    options.replaceChildren(
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
    options.replaceChildren(li);
  }

  options.hidden = false;
  input.setAttribute("aria-expanded", "true");
  highlight(active);
}

function closeList() {
  options.hidden = true;
  input.setAttribute("aria-expanded", "false");
  input.removeAttribute("aria-activedescendant");
}

function highlight(i) {
  active = i;
  [...options.children].forEach((li, n) => li.setAttribute("aria-selected", n === i));
  if (i >= 0) {
    input.setAttribute("aria-activedescendant", `theme-option-${i}`);
    options.children[i].scrollIntoView({ block: "nearest" });
  } else {
    input.removeAttribute("aria-activedescendant");
  }
}

function choose(theme) {
  const changed = theme !== chosen;
  chosen = theme;
  input.value = theme.name;
  hint.textContent = theme.hint;
  closeList();
  if (changed) onChange(theme);
}

input.addEventListener("focus", () => {
  input.select(); // typing replaces the old name
  openList();
});

input.addEventListener("input", () => openList(input.value));

input.addEventListener("blur", () => {
  closeList();
  if (chosen) input.value = chosen.name; // half-typed text goes back to the chosen theme
});

input.addEventListener("keydown", (e) => {
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
    if (chosen) input.value = chosen.name;
  }
});

// Tapping the list or the arrow must not take focus away from the text box,
// or the list would close before the tap lands.
for (const el of [options, toggle]) {
  el.addEventListener("mousedown", (e) => e.preventDefault());
}

toggle.addEventListener("click", () => {
  if (isOpen()) closeList();
  else if (document.activeElement === input) openList();
  else input.focus();
});

export async function loadThemes() {
  try {
    const res = await fetch("api/themes");
    themes = await res.json();
    input.disabled = false;
    if (themes.length) {
      input.placeholder = "Pick or type a theme";
      // Keep the theme already picked (with its new name, if it changed).
      choose(themes.find((t) => t.id === chosen?.id) || themes[0]);
    } else {
      input.placeholder = "No themes yet";
      hint.textContent = "Add a theme file to the theme folder.";
    }
  } catch {
    input.placeholder = "Couldn't load themes";
    hint.textContent = "Is the server running?";
  }
}
