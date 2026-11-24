// The Theme tab: pick a theme from the list to see what it does behind the
// scenes. The words it adds around your prompt, what it tells the model to
// avoid, the model and LoRAs it uses, and its settings. "Change" opens a
// form to edit the theme. The New tab (#theme/new) makes a new theme.

import { SAMPLERS, editTheme } from "./theme-edit.js";
import { loadThemes } from "./theme-picker.js";

const box = document.getElementById("theme-info");
const newBox = document.getElementById("theme-new");

const CHOSEN_KEY = "imageai.themeTab"; // the theme last looked at, on this phone

const BACKENDS = {
  "diffusers-sdxl": "SDXL model, run with diffusers (PyTorch)",
  mflux: "Model folder, run with mflux (Apple MLX, Mac only)",
};

export function loadThemeInfo(sub) {
  const mode = sub === "new" ? "new" : "edit";
  document.querySelectorAll("#view-theme [data-subview]").forEach((el) => {
    if (el.dataset.subview === mode) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  box.hidden = mode === "new";
  newBox.hidden = mode !== "new";
  if (mode === "new") showNew();
  else showEdit();
}

// New: the same form as Change, empty, starting from the Custom tab's
// starting words and settings (server/settings.json).
async function showNew(again = false) {
  // Coming back to the tab keeps what was typed; "Start again" clears it.
  if (newBox.childElementCount && !again) return;
  const card = el("article", "card theme-card");
  newBox.replaceChildren(card);
  let start;
  try {
    start = await (await fetch("api/custom")).json();
  } catch {
    card.append(el("p", "muted", "Couldn't load. Is the server running?"));
    return;
  }
  const blank = {
    name: "",
    hint: "",
    prompt_before: start.prompt_before,
    prompt_after: start.prompt_after,
    negative: start.negative,
    model: { file: start.model },
    loras: [],
    settings: { width: start.width, height: start.height, steps: start.steps, guidance: start.guidance, scheduler: start.scheduler },
  };
  editTheme(card, blank, (made) => {
    if (!made) return showNew(true);
    // Show the new theme on the Edit tab, and in the picker on Create.
    try {
      localStorage.setItem(CHOSEN_KEY, made.id);
    } catch {}
    loadThemes();
    newBox.replaceChildren();
    location.hash = "#theme";
  }, { isNew: true });
}

async function showEdit() {
  try {
    const res = await fetch("api/themes/details");
    const themes = await res.json();
    if (!themes.length) {
      box.innerHTML = `<p class="muted">No themes yet. Add a theme file to the theme folder.</p>`;
      return;
    }
    showChooser(themes);
  } catch {
    box.innerHTML = `<p class="muted">Couldn't load the themes. Is the server running?</p>`;
  }
}

// Small helper: an element with a class and text.
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function section(title, ...children) {
  const part = el("section", "theme-part");
  part.append(el("h3", "", title), ...children);
  return part;
}

function rows(pairs) {
  const list = el("dl", "facts");
  for (const [label, value] of pairs) list.append(el("dt", "", label), el("dd", "", value));
  return list;
}

function fileLine(file, found, extra) {
  const line = el("p", "file");
  line.append(el("span", "file-name", file));
  if (extra) line.append(el("span", "muted", ` ${extra}`));
  if (!found) line.append(el("span", "missing", "file not found"));
  return line;
}

// The drop list on top, the chosen theme's card under it.
function showChooser(themes) {
  const chooser = el("label", "card field theme-chooser");
  const list = el("select", "text-input");
  list.id = "theme-tab-choice";
  for (const theme of themes) {
    const option = el("option", "", theme.name);
    option.value = theme.id;
    list.append(option);
  }
  chooser.append(el("span", "label", "Theme"), list);
  const root = el("article", "card theme-card");

  let chosen = "";
  try {
    chosen = localStorage.getItem(CHOSEN_KEY) || "";
  } catch {}
  list.value = themes.some((t) => t.id === chosen) ? chosen : themes[0].id;

  const show = () => {
    const theme = themes.find((t) => t.id === list.value);
    try {
      localStorage.setItem(CHOSEN_KEY, theme.id);
    } catch {}
    fill(root, theme, (saved) => {
      Object.assign(theme, saved); // a new name shows in the list too
      list.selectedOptions[0].textContent = saved.name;
    });
  };
  list.addEventListener("change", show);
  box.replaceChildren(chooser, root);
  show();
}

function fill(root, theme, onSaved) {
  root.replaceChildren();
  const head = el("div", "theme-head");
  const change = el("button", "button small-button", "Change");
  change.type = "button";
  change.addEventListener("click", () =>
    editTheme(root, theme, (saved) => {
      fill(root, saved || theme, onSaved);
      if (saved) {
        loadThemes(); // the picker on Create shows the new name
        onSaved(saved);
      }
      root.scrollIntoView({ block: "start" });
    })
  );
  head.append(el("h2", "theme-title", theme.name), change);
  root.append(head);
  if (theme.hint) root.append(el("p", "muted", theme.hint));
  if (theme.notes) root.append(el("p", "small notes", theme.notes));

  // Your words in the middle of the theme's words.
  const flow = el("p", "prompt-flow");
  if (theme.prompt_before) flow.append(el("span", "words", theme.prompt_before));
  flow.append(el("span", "yours", "your prompt"));
  if (theme.prompt_after) flow.append(el("span", "words", theme.prompt_after));

  const words = el("div", "theme-words");
  words.append(
    section("What it adds to your prompt", flow),
    section("What it tells the model to avoid", el("p", "words block", theme.negative || "Nothing")),
    section("Always avoided, in every theme (safety)", el("p", "words block", theme.safety_negative))
  );

  const s = theme.settings;
  const loras = theme.loras.length
    ? theme.loras.map((l) => fileLine(l.file, l.found, `strength ${l.weight}`))
    : [el("p", "muted", "None")];
  const facts = el("div", "theme-facts");
  facts.append(
    section("Model", fileLine(theme.model.file, theme.model.found), el("p", "muted small", BACKENDS[theme.backend] || theme.backend)),
    section("LoRAs", ...loras),
    section(
      "Settings",
      rows([
        ["Picture size", `${s.width} × ${s.height}`],
        ["Steps", `${s.steps} (more = more detail, slower)`],
        ["Guidance", `${s.guidance} (how closely it follows the prompt)`],
        // mflux models have no sampler to choose, and the 3060 settings are for SDXL.
        ...(theme.backend === "mflux"
          ? []
          : [
              ["Sampler", SAMPLERS[s.scheduler] || s.scheduler],
              ["3060 settings", theme.use_3060_settings ? "On (Settings page)" : "Off (Settings page)"],
            ]),
      ])
    )
  );

  const body = el("div", "theme-body");
  body.append(words, facts);
  root.append(body);
}
