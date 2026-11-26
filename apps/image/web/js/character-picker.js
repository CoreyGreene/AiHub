// "Pick" beside a character name box: lists every saved character by name, with a search box (Enter picks the
// first one found); tapping one puts its name in the box (Create's Save, or Staging's "Add to
// character"), so the pictures go to that character.

const chooser = document.getElementById("character-chooser");
const list = document.getElementById("chooser-list");
const search = document.getElementById("chooser-search");
let everyone = []; // every saved character, before the search
let input = document.getElementById("character"); // the box being filled

// Open the list for a name box.
export function pickCharacter(box) {
  input = box;
  open();
}

document.getElementById("pick-character").addEventListener("click", () => pickCharacter(document.getElementById("character")));
document.getElementById("chooser-close").addEventListener("click", () => chooser.close());
// Tapping the dark area around the sheet closes it too.
chooser.addEventListener("click", (event) => {
  if (event.target === chooser) chooser.close();
});

async function open() {
  list.innerHTML = `<p class="muted">Loading…</p>`;
  search.value = "";
  chooser.showModal();
  search.focus();
  try {
    const res = await fetch("api/characters");
    everyone = await res.json();
    if (!everyone.length) {
      list.innerHTML = `<p class="muted">No characters yet. Type a name, make a picture and press Save.</p>`;
      return;
    }
    show();
  } catch {
    list.innerHTML = `<p class="muted">Couldn't load the characters. Is the server running?</p>`;
  }
}

// The characters whose name has the search words in it.
function show() {
  const words = search.value.trim().toLowerCase();
  const found = everyone.filter((c) => c.name.toLowerCase().includes(words));
  if (found.length) list.replaceChildren(...found.map(choice));
  else list.innerHTML = `<p class="muted">No character called “${search.value.trim().replace(/[<>&"]/g, "")}”.</p>`;
}

search.addEventListener("input", show);
// Enter picks the first one found.
search.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing) {
    event.preventDefault();
    list.querySelector(".choice")?.click();
  }
});

function choice(character) {
  const item = document.createElement("button");
  item.type = "button";
  item.className = "choice";
  item.textContent = character.name;
  item.classList.toggle("chosen", character.name.toLowerCase() === input.value.trim().toLowerCase());
  item.addEventListener("click", () => {
    input.value = character.name;
    input.dispatchEvent(new Event("input")); // Save buttons update their wording
    chooser.close();
  });
  return item;
}
