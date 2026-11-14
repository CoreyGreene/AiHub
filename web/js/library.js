// The Library tab: every saved character, shown with its first picture.

const list = document.getElementById("library-list");

export async function loadLibrary() {
  try {
    const res = await fetch("api/characters");
    const characters = await res.json();
    if (!characters.length) {
      list.innerHTML = `<p class="muted">No characters yet. Make a picture, type a name and press Save.</p>`;
      return;
    }
    list.replaceChildren(...characters.map(card));
  } catch {
    list.innerHTML = `<p class="muted">Couldn't load the library. Is the server running?</p>`;
  }
}

function card(character) {
  const item = document.createElement("article");
  item.className = "character";
  item.innerHTML = `<img alt="" loading="lazy"><h3></h3><p class="muted"></p>`;
  item.querySelector("img").src = character.cover;
  item.querySelector("h3").textContent = character.name;
  item.querySelector("p").textContent = `${character.count} picture${character.count === 1 ? "" : "s"}`;
  return item;
}
