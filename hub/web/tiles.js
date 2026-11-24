// The tile page: one tile per tool, with whether it's running. The bar
// (bar.js) fetches the status every few seconds and shares it here.

const tiles = document.getElementById("tiles");

const WORDS = {
  running: "Ready",
  starting: "Starting…",
  stopped: "Stopped",
  failed: "Didn't start",
  not_set_up: "Not set up yet",
};

function show(data) {
  tiles.replaceChildren(...data.apps.map((tool) => {
    const a = document.createElement("a");
    a.className = "tile" + (tool.state === "not_set_up" ? " off" : "");
    a.href = `/${tool.id}/`;
    const name = document.createElement("strong");
    name.textContent = tool.name;
    const about = document.createElement("span");
    about.className = "muted";
    about.textContent = tool.about;
    const badge = document.createElement("span");
    const inUse = tool.state === "running" && tool.memory >= 1e9; // a model is loaded
    badge.className = `badge ${inUse ? "running" : tool.state === "running" ? "ready" : tool.state}`;
    badge.textContent = inUse ? `In use · ${(tool.memory / 1e9).toFixed(0)} GB` : WORDS[tool.state] || tool.state;
    a.append(name, about, badge);
    return a;
  }));
}

window.addEventListener("aihub-status", (e) => show(e.detail));
