// The Theme tab: what each theme does behind the scenes. The words it adds
// around your prompt, what it tells the model to avoid, the model and LoRAs
// it uses, and its settings. Read only; themes are changed in their files.

const box = document.getElementById("theme-info");

const BACKENDS = { "diffusers-sdxl": "SDXL model, run with diffusers (PyTorch)" };
const SAMPLERS = { euler_a: "Euler a", euler: "Euler", "dpm++": "DPM++" };

export async function loadThemeInfo() {
  try {
    const res = await fetch("api/themes/details");
    const themes = await res.json();
    if (!themes.length) {
      box.innerHTML = `<p class="muted">No themes yet. Add a theme file to the theme folder.</p>`;
      return;
    }
    box.replaceChildren(...themes.map(card));
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

function card(theme) {
  const root = el("article", "card theme-card");
  root.append(el("h2", "theme-title", theme.name));
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
        ["Sampler", SAMPLERS[s.scheduler] || s.scheduler],
        ["3060 settings", theme.use_3060_settings ? "On (Settings page)" : "Off (Settings page)"],
      ])
    )
  );

  const body = el("div", "theme-body");
  body.append(words, facts);
  root.append(body);
  return root;
}
