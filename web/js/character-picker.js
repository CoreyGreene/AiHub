// "Pick" beside the character name: lists every saved character by name; tapping
// one puts its name in the box, so Save adds new videos to it.

const input = document.getElementById("character");
const chooser = document.getElementById("character-chooser");
const list = document.getElementById("chooser-list");

document.getElementById("pick-character").addEventListener("click", open);
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
      list.innerHTML = `<p class="muted">No characters yet. Type a name, make a video and press Save.</p>`;
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
