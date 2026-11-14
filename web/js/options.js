// The Advanced tab's options: detail, face lines, light, outlines. Each adds
// words to the prompt (and to what the model avoids); no extra time.
// The choices come from server/options.json; the phone remembers yours.

const box = document.getElementById("picture-options");
const choicesBox = document.getElementById("option-choices");
const KEY = "imageai.options";

let remembered = {};
try {
  remembered = JSON.parse(localStorage.getItem(KEY)) || {};
} catch {}

function remember() {
  try {
    localStorage.setItem(KEY, JSON.stringify(chosenOptions()));
  } catch {}
}

export async function loadOptions() {
  try {
    const res = await fetch("api/options");
    const data = await res.json();
    choicesBox.replaceChildren(...data.choices.map(choiceRow));
    box.hidden = false;
  } catch {
    box.hidden = true; // pictures still work without the options
  }
}

// One choice: its name, then a row of buttons (one picked at a time).
function choiceRow(choice) {
  const row = document.createElement("div");
  row.className = "option-row";
  const name = document.createElement("span");
  name.className = "option-name";
  name.id = `option-${choice.id}`;
  name.textContent = choice.label;
  const group = document.createElement("div");
  group.className = "segmented";
  group.setAttribute("role", "radiogroup");
  group.setAttribute("aria-labelledby", name.id);
  group.dataset.option = choice.id;
  const ids = choice.values.map((v) => v.id);
  const picked = ids.includes(remembered[choice.id]) ? remembered[choice.id] : ids[0];
  for (const value of choice.values) {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "radio");
    b.dataset.value = value.id;
    b.textContent = value.label;
    b.setAttribute("aria-checked", value.id === picked);
    b.addEventListener("click", () => {
      group.querySelectorAll("[role=radio]").forEach((o) => o.setAttribute("aria-checked", o === b));
      remember();
    });
    group.append(b);
  }
  row.append(name, group);
  return row;
}

export function chosenOptions() {
  const out = {};
  for (const group of choicesBox.querySelectorAll("[data-option]")) {
    const on = group.querySelector('[aria-checked="true"]');
    if (on) out[group.dataset.option] = on.dataset.value;
  }
  return out;
}
