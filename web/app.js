// The page only shows things and talks to the server.
// All image work happens on the server (server/generation.py).

const els = {
  form: document.getElementById("make"),
  themes: document.getElementById("theme-list"),
  prompt: document.getElementById("prompt"),
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

async function loadThemes() {
  try {
    const res = await fetch("api/themes");
    const themes = await res.json();
    els.themes.replaceChildren(
      ...themes.map((t, i) => {
        const label = document.createElement("label");
        label.className = "theme";
        label.innerHTML = `<input type="radio" name="theme"><span class="name"></span><span class="hint"></span>`;
        const input = label.querySelector("input");
        input.value = t.id;
        input.checked = i === 0;
        label.querySelector(".name").textContent = t.name;
        label.querySelector(".hint").textContent = t.hint;
        return label;
      })
    );
  } catch {
    els.themes.innerHTML = `<p class="muted">Couldn't load themes. Is the server running?</p>`;
  }
}

async function onGenerate(event) {
  event.preventDefault();
  const theme = els.form.querySelector("input[name=theme]:checked")?.value;
  const prompt = els.prompt.value.trim();

  if (!theme) return showNote("Pick a theme first", "");
  if (!prompt) {
    els.prompt.focus();
    return showNote("Type a prompt first", "Describe the picture you want.");
  }

  els.button.disabled = true;
  els.button.textContent = "Working…";
  try {
    const res = await fetch("api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme, prompt }),
    });
    const data = await res.json();
    if (data.status === "not_connected") {
      showNote("Not connected yet", data.message);
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

els.form.addEventListener("submit", onGenerate);
loadThemes();
