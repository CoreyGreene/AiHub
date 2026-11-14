// Changing a theme on the Theme tab: a form in place of the theme's card.
// Saving writes the theme file on the server; the next picture uses it.

let choicesWait = null; // model and LoRA files here, and the samplers

export function choices() {
  choicesWait ??= fetch("api/themes/choices").then((res) => res.json());
  return choicesWait;
}

export const SAMPLERS = { euler_a: "Euler a", euler: "Euler", "dpm++": "DPM++", "dpm++_karras": "DPM++ 2M Karras" };

export function field(label, input, help) {
  const box = document.createElement("label");
  box.className = "field";
  const title = document.createElement("span");
  title.className = "label";
  title.textContent = label;
  box.append(title, input);
  if (help) {
    const note = document.createElement("span");
    note.className = "muted small field-help";
    note.textContent = help;
    box.append(note);
  }
  return box;
}

function textInput(value, maxLength = 80) {
  const input = document.createElement("input");
  input.type = "text";
  input.className = "text-input";
  input.maxLength = maxLength;
  input.value = value;
  return input;
}

export function textArea(value) {
  const area = document.createElement("textarea");
  area.rows = 4;
  area.value = value;
  return area;
}

export function numberInput(value, { min, max, step }) {
  const input = document.createElement("input");
  input.type = "number";
  input.inputMode = step < 1 ? "decimal" : "numeric";
  input.className = "text-input";
  Object.assign(input, { min, max, step, value });
  return input;
}

export function select(options, value, labels = {}) {
  const box = document.createElement("select");
  box.className = "text-input";
  for (const option of options) box.append(new Option(labels[option] || option, option));
  // A file the theme names but that isn't here still shows, marked.
  if (value && !options.includes(value)) box.append(new Option(`${value} (not found)`, value));
  box.value = value;
  return box;
}

export function button(text, className, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = className;
  b.textContent = text;
  b.addEventListener("click", onClick);
  return b;
}

// LoRAs: one row each (file, strength, remove), plus "Add a LoRA".
// Returns { box, values() } where values() is [{ file, weight }].
export function loraEditor(files, start) {
  const rows = document.createElement("div");
  rows.className = "lora-rows";
  function addLora(file, weight) {
    const row = document.createElement("div");
    row.className = "lora-row";
    const pick = select(files, file);
    pick.setAttribute("aria-label", "LoRA file");
    const label = document.createElement("span");
    label.className = "muted small";
    label.textContent = "Strength";
    const strength = numberInput(weight, { min: -2, max: 2, step: 0.05 });
    strength.setAttribute("aria-label", "Strength");
    row.append(pick, label, strength, button("Remove", "button small-button", () => row.remove()));
    rows.append(row);
  }
  start.forEach((l) => addLora(l.file, l.weight));
  // A new row starts with a LoRA that isn't in the list yet.
  const add = button("Add a LoRA", "button small-button", () => {
    const used = [...rows.querySelectorAll("select")].map((pick) => pick.value);
    addLora(files.find((file) => !used.includes(file)) || files[0], 0.8);
  });
  add.disabled = !files.length;
  const box = document.createElement("div");
  box.className = "field";
  box.append(Object.assign(document.createElement("span"), { className: "label", textContent: "LoRAs" }), rows, add);
  return {
    box,
    values: () =>
      [...rows.children].map((row) => ({
        file: row.querySelector("select").value,
        weight: Number(row.querySelector("input").value),
      })),
  };
}

// Show the form inside `card`. onDone(theme) gets the saved theme, or null
// for Cancel.
export async function editTheme(card, theme, onDone) {
  card.replaceChildren(Object.assign(document.createElement("p"), { className: "muted", textContent: "Loading…" }));
  let found;
  try {
    found = await choices();
  } catch {
    card.querySelector("p").textContent = "Couldn't load the model list. Is the server running?";
    return;
  }
  const s = theme.settings;

  const name = textInput(theme.name, 40);
  const hint = textInput(theme.hint, 80);
  const before = textArea(theme.prompt_before);
  const after = textArea(theme.prompt_after);
  const negative = textArea(theme.negative);
  const model = select(found.models, theme.model.file);
  const width = numberInput(s.width, { min: 512, max: 2048, step: 8 });
  const height = numberInput(s.height, { min: 512, max: 2048, step: 8 });
  const steps = numberInput(s.steps, { min: 1, max: 100, step: 1 });
  const guidance = numberInput(s.guidance, { min: 0, max: 30, step: 0.5 });
  const sampler = select(found.schedulers, s.scheduler, SAMPLERS);

  const loras = loraEditor(found.loras, theme.loras);
  const size = document.createElement("div");
  size.className = "two-up";
  size.append(field("Width", width), field("Height", height));
  const more = document.createElement("div");
  more.className = "two-up";
  more.append(field("Steps", steps, "More = more detail, slower"), field("Guidance", guidance, "How closely it follows the prompt"));

  const error = document.createElement("p");
  error.className = "error-line";
  error.hidden = true;

  const save = button("Save theme", "primary", onSave);
  const cancel = button("Cancel", "button", () => onDone(null));
  const actions = document.createElement("div");
  actions.className = "actions";
  actions.append(cancel);

  const heading = document.createElement("h2");
  heading.className = "theme-title";
  heading.textContent = `Change ${theme.name}`;

  card.replaceChildren(
    heading,
    field("Name", name),
    field("Hint", hint, "The short line under the theme in the picker"),
    field("Words before your prompt", before),
    field("Words after your prompt", after),
    field("What to avoid", negative, "The safety words are always added too"),
    field("Model", model),
    loras.box,
    size,
    more,
    field("Sampler", sampler),
    error,
    save,
    actions
  );
  name.focus();

  async function onSave() {
    error.hidden = true;
    save.disabled = true;
    save.textContent = "Saving…";
    const body = {
      name: name.value,
      hint: hint.value,
      prompt_before: before.value,
      prompt_after: after.value,
      negative: negative.value,
      model: model.value,
      loras: loras.values(),
      width: Number(width.value),
      height: Number(height.value),
      steps: Number(steps.value),
      guidance: Number(guidance.value),
      scheduler: sampler.value,
    };
    try {
      const res = await fetch(`api/themes/${encodeURIComponent(theme.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Some boxes need a number.");
      }
      onDone(data);
    } catch (err) {
      error.textContent = err.message || "Couldn't save. Is the server running?";
      error.hidden = false;
      save.disabled = false;
      save.textContent = "Save theme";
    }
  }
}
