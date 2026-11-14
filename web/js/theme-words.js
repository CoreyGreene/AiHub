// The Advanced tab: the chosen theme's words (before and after your prompt,
// and what to avoid), shown so you can change them for these pictures. The
// theme file isn't changed; picking another theme, or "Put back", shows
// that theme's own words again.

import { chosenTheme, whenThemeChanges } from "./theme-picker.js";
import { field, textArea } from "./theme-edit.js";

const box = document.getElementById("theme-words-fields");
const putBack = document.getElementById("theme-words-reset");

let form = null;
let filledFor = null; // the theme id the boxes show

// Fill the boxes with the theme's own words (fresh from the server, so
// changes made on the Theme tab show up).
async function fill(theme) {
  if (!theme) return;
  filledFor = theme.id;
  try {
    const res = await fetch("api/themes/details");
    const found = (await res.json()).find((t) => t.id === theme.id);
    if (!found || filledFor !== theme.id) return; // another theme was picked meanwhile
    form = {
      before: textArea(found.prompt_before),
      after: textArea(found.prompt_after),
      negative: textArea(found.negative),
    };
    for (const area of Object.values(form)) area.rows = 2;
    box.replaceChildren(
      field("Words before your prompt", form.before),
      field("Words after your prompt", form.after),
      field("What to avoid", form.negative, "The safety words are always added too")
    );
    putBack.hidden = false;
  } catch {
    form = null;
    box.innerHTML = `<p class="muted">Couldn't load this theme's words. The theme's own will be used.</p>`;
  }
}

// Advanced tab shown: fill in, unless it already shows this theme (keeps your changes).
export function showThemeWords() {
  const theme = chosenTheme();
  if (theme && theme.id !== filledFor) fill(theme);
}

// What Generate sends: null means "the theme's own words".
export function themeWords() {
  if (!form) return null;
  return { prompt_before: form.before.value, prompt_after: form.after.value, negative: form.negative.value };
}

whenThemeChanges((theme) => {
  form = null;
  filledFor = null;
  if (document.getElementById("view-create").dataset.mode === "advanced") fill(theme);
});
putBack.addEventListener("click", () => fill(chosenTheme()));
