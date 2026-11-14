// Adding a model or LoRA file from the page: drop it on the box or press
// "Choose a file". The server checks the name and disk space first, then
// the file is sent with a progress bar (a model is several GB). It lands in
// the models or LoRA folder; onAdded(fileName) is told when it's there.

// A file dropped outside a box would make the browser leave the page to
// show it. Stop that everywhere; the boxes handle their own drops.
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());

const gb = (bytes) => `${(bytes / 1024 ** 3).toFixed(1)} GB`;

function size(bytes) {
  return bytes >= 1024 ** 3 ? gb(bytes) : `${Math.max(1, Math.round(bytes / 1024 ** 2))} MB`;
}

// kind: "model" or "lora". onBusy(true/false) while a file is being sent.
export function uploadBox(kind, { onAdded, onBusy = () => {} }) {
  const what = kind === "model" ? "model" : "LoRA";
  const box = document.createElement("div");
  box.className = "drop-zone";
  box.innerHTML = `
    <p class="small drop-text"></p>
    <input type="file" accept=".safetensors" hidden>
    <button type="button" class="button small-button drop-choose">Choose a file</button>
    <div class="drop-progress" hidden>
      <div class="bar"><span></span></div>
      <p class="small muted drop-status"></p>
      <button type="button" class="button small-button drop-stop">Stop</button>
    </div>
    <p class="small drop-message" hidden></p>`;
  box.querySelector(".drop-text").textContent =
    kind === "model"
      ? "Add a new model: drop a .safetensors file here, or choose one. A video model (for example Wan)."
      : "Add a new LoRA: drop a .safetensors file here, or choose one. It must be made for the same video model.";

  const input = box.querySelector("input");
  const choose = box.querySelector(".drop-choose");
  const progress = box.querySelector(".drop-progress");
  const bar = box.querySelector(".bar span");
  const status = box.querySelector(".drop-status");
  const message = box.querySelector(".drop-message");
  let sending = null; // the upload in progress
  let stopped = false; // Stop was pressed

  function tell(text, good) {
    message.textContent = text;
    message.className = `small drop-message ${good ? "good" : "error-line"}`;
    message.hidden = false;
  }

  choose.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    if (input.files[0]) send(input.files[0]);
    input.value = "";
  });
  box.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (!sending) box.classList.add("over");
  });
  box.addEventListener("dragleave", () => box.classList.remove("over"));
  box.addEventListener("drop", (event) => {
    event.preventDefault();
    box.classList.remove("over");
    const file = event.dataTransfer.files[0];
    if (file && !sending) send(file);
  });
  box.querySelector(".drop-stop").addEventListener("click", () => {
    stopped = true;
    sending?.abort();
  });

  async function send(file) {
    message.hidden = true;
    if (!file.name.toLowerCase().endsWith(".safetensors")) {
      tell(`Only .safetensors files can be added. ${file.name} isn't one.`);
      return;
    }
    const url = `api/files/${kind}/${encodeURIComponent(file.name)}`;
    try {
      const res = await fetch(`${url}/check?size=${file.size}`);
      if (!res.ok) throw new Error((await res.json()).detail);
    } catch (err) {
      tell(err.message || "Couldn't reach the server.");
      return;
    }

    choose.hidden = true;
    progress.hidden = false;
    bar.style.width = "0";
    status.textContent = `Sending ${file.name}…`;
    onBusy(true);
    // XMLHttpRequest, not fetch: it can tell how much has been sent.
    const xhr = new XMLHttpRequest();
    sending = xhr;
    stopped = false;
    xhr.open("PUT", url);
    xhr.upload.addEventListener("progress", (event) => {
      bar.style.width = `${(event.loaded / event.total) * 100}%`;
      status.textContent = event.loaded < event.total
        ? `Sending ${file.name}: ${size(event.loaded)} of ${size(event.total)}`
        : `Checking ${file.name}…`;
    });
    xhr.addEventListener("loadend", () => {
      sending = null;
      choose.hidden = false;
      progress.hidden = true;
      onBusy(false);
      let data = {};
      try {
        data = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status === 200) {
        tell(`${data.file} added and picked.`, true);
        onAdded(data.file);
      } else if (stopped) {
        tell("Stopped. Nothing was added.");
      } else if (xhr.status === 0) {
        tell("The upload stopped part way. Is the server running?");
      } else {
        tell(data.detail || "Couldn't add that file.");
      }
    });
    xhr.send(file);
  }

  box.setAttribute("aria-label", `Add a ${what} file`);
  return box;
}
