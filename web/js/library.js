// The Library tab: every saved character, shown with its first picture.
// Tap one to open it (#library/<folder>) and see all of its pictures.

const list = document.getElementById("library-list");
const title = document.getElementById("library-title");
const count = document.getElementById("library-count");
const back = document.getElementById("library-back");

const pictures = (n) => `${n} picture${n === 1 ? "" : "s"}`;

export function loadLibrary(folder) {
  window.scrollTo(0, 0);
  if (folder) showCharacter(decodeURIComponent(folder));
  else showAll();
}

async function showAll() {
  title.textContent = "Library";
  back.hidden = count.hidden = true;
  list.className = "library-grid";
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
  const item = document.createElement("a");
  item.className = "character";
  item.href = `#library/${encodeURIComponent(character.folder)}`;
  item.innerHTML = `<img alt="" loading="lazy"><h3></h3><p class="muted"></p>`;
  item.querySelector("img").src = character.cover;
  item.querySelector("h3").textContent = character.name;
  item.querySelector("p").textContent = pictures(character.count);
  return item;
}

async function showCharacter(folder) {
  back.hidden = false;
  title.textContent = "…";
  count.hidden = true;
  list.className = "character-pictures";
  list.innerHTML = `<p class="muted">Loading…</p>`;
  try {
    const res = await fetch(`api/characters/${encodeURIComponent(folder)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    title.textContent = data.name;
    count.textContent = `${pictures(data.pictures.length)}. To add more, make a picture with the name ${data.name} and press Save.`;
    count.hidden = false;
    list.replaceChildren(...data.pictures.map(pictureCard));
  } catch (err) {
    title.textContent = "Library";
    list.innerHTML = `<p class="muted"></p>`;
    list.firstChild.textContent = err.message || "Couldn't load this character. Is the server running?";
  }
}

function pictureCard(pic) {
  const item = document.createElement("article");
  item.className = "saved-picture";
  item.innerHTML = `
    <a class="saved-image" target="_blank" rel="noopener"><img alt="" loading="lazy"></a>
    <div class="saved-info">
      <p class="saved-prompt"></p>
      <p class="muted small saved-meta"></p>
      <a class="button small-button" download>Download</a>
    </div>`;
  item.querySelector(".saved-image").href = pic.image;
  item.querySelector("img").src = pic.image;
  item.querySelector(".saved-prompt").textContent = pic.prompt;
  const made = pic.made ? new Date(pic.made).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
  item.querySelector(".saved-meta").textContent = [pic.theme, made].filter(Boolean).join(" · ");
  item.querySelector("[download]").href = `${pic.image}?download=1`;
  return item;
}
