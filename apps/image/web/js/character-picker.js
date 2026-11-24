// "Pick" beside a character name box: lists every saved character by name;
// tapping one puts its name in the box (Create's Save, or Staging's "Add to
// character"), so the pictures go to that character.

const chooser = document.getElementById("character-chooser");
const list = document.getElementById("chooser-list");
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
  chooser.showModal();
  try {
    const res = await fetch("api/characters");
    const characters = await res.json();
    if (!characters.length) {
      list.innerHTML = `<p class="muted">No characters yet. Type a name, make a picture and press Save.</p>`;
      return;
    }
    list.replaceChildren(...characters.map(choice));
  } catch {
    list.innerHTML = `<p class="muted">Couldn't load the characters. Is the server running?</p>`;
  }
}

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
