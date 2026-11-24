// The Custom tab: your own theme, no theme file behind it. Pick the model
// and LoRAs, write the words around your prompt, set the size and steps.
// It starts from the server's defaults (settings.json "custom"), or from a
// picture's settings (Library → Copy settings); what you change stays while
// the page is open.

import { SAMPLERS, choices, field, loraEditor, numberInput, select, textArea } from "./theme-edit.js";

const box = document.getElementById("custom-fields");
let form = null;
let building = null; // the form being built (it waits for the server)
const copiedNote = document.getElementById("copied-note");

function pair(a, b) {
  const row = document.createElement("div");
  row.className = "two-up";
  row.append(a, b);
  return row;
}

// Build the form (first time on the Custom tab, or "Start again"), or from
// a picture's settings when `from` is given.
export function fillCustom(force = false, from = null) {
  if (!force && (form || building)) return building;
  form = null;
  building = build(from).finally(() => (building = null));
  return building;
}

async function build(from) {
  try {
    const [found, defaults] = await Promise.all([choices(), from || fetch("api/custom").then((res) => res.json())]);
    const start = from || defaults;
    const f = {
      model: select([...found.models], start.model),
      loras: loraEditor([...found.loras], start.loras || []),
      before: textArea(start.prompt_before),
      after: textArea(start.prompt_after),
      negative: textArea(start.negative),
      width: numberInput(start.width, { min: 512, max: 2048, step: 8 }),
      height: numberInput(start.height, { min: 512, max: 2048, step: 8 }),
      steps: numberInput(start.steps, { min: 1, max: 100, step: 1 }),
      guidance: numberInput(start.guidance, { min: 0, max: 30, step: 0.5 }),
      sampler: select(found.schedulers, start.scheduler, SAMPLERS),
    };
    box.replaceChildren(
      field("Model", f.model),
      f.loras.box,
      field("Words before your prompt", f.before),
      field("Words after your prompt", f.after),
      field("What to avoid", f.negative, "The safety words are always added too"),
      pair(field("Width", f.width), field("Height", f.height)),
      pair(field("Steps", f.steps, "More = more detail, slower"), field("Guidance", f.guidance, "How closely it follows the prompt")),
      field("Sampler", f.sampler)
    );
    form = f;
  } catch {
    box.innerHTML = `<p class="muted">Couldn't load the model list. Is the server running?</p>`;
  }
}

// What Generate sends: null if the form isn't ready.
export function customValues() {
  if (!form) return null;
  return {
    model: form.model.value,
    loras: form.loras.values(),
    prompt_before: form.before.value,
    prompt_after: form.after.value,
    negative: form.negative.value,
    width: Number(form.width.value),
    height: Number(form.height.value),
    steps: Number(form.steps.value),
    guidance: Number(form.guidance.value),
    scheduler: form.sampler.value,
  };
}

document.getElementById("custom-reset").addEventListener("click", () => {
  copiedNote.hidden = true;
  fillCustom(true);
});
