// The hub's bar, added to the top of every page (the tile page and each tool's).
// Shows which tools are running and how much memory each uses, with a Stop button.
// Self-contained: its own styles, all names start with "aihub-" so they can't clash.

(() => {
  if (document.getElementById("aihub-bar")) return;

  const here = location.pathname.split("/")[1] || ""; // the tool this page belongs to ("" = tiles)
  const css = document.createElement("style");
  css.textContent = `
    #aihub-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px;
      margin: 0 0 4px; padding: 8px 0; border-bottom: 1px solid #34343f;
      font: 14px/1.3 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #ececf1; }
    #aihub-bar a.aihub-home { color: #ececf1; text-decoration: none; font-weight: 700;
      padding: 6px 10px; border-radius: 10px; background: #20202a; border: 1px solid #34343f; }
    .aihub-chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 4px 3px 10px;
      border-radius: 999px; background: #20202a; border: 1px solid #34343f; white-space: nowrap; }
    .aihub-chip.aihub-here { border-color: #7c6cff; }
    .aihub-chip .aihub-dot { width: 8px; height: 8px; border-radius: 50%; background: #3ecf8e; }
    .aihub-chip.aihub-starting .aihub-dot { background: #f5b942; }
    .aihub-chip a { color: inherit; text-decoration: none; }
    .aihub-mem { color: #9a9aa8; }
    .aihub-stop { font: inherit; font-size: 13px; color: #ececf1; background: #34343f; border: 0;
      border-radius: 999px; padding: 4px 10px; min-height: 28px; cursor: pointer; }
    .aihub-stop.aihub-sure { background: #d9534f; }
    .aihub-mac { margin-left: auto; color: #9a9aa8; font-size: 13px; white-space: nowrap; }
    .aihub-none { color: #9a9aa8; }
  `;
  const bar = document.createElement("div");
  bar.id = "aihub-bar";
  document.head.append(css);
  document.body.prepend(bar);

  const IN_USE = 1e9; // bytes: more than this means a model is loaded
  const gb = (bytes) => (bytes / 1e9 >= 10 ? (bytes / 1e9).toFixed(0) : (bytes / 1e9).toFixed(1)) + " GB";
  const make = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  };

  // The bar's parts are made once and then only their words change, so a tap
  // never lands on a button that was just replaced.
  const home = make("a", "aihub-home", "⌂ AI Hub");
  home.href = "/";
  const none = make("span", "aihub-none", "Nothing running");
  const mac = make("span", "aihub-mac");
  const chips = new Map(); // tool id -> {el, mem}

  function chip(tool) {
    const el = make("span", "aihub-chip");
    const name = make("a", "", tool.name);
    name.href = `/${tool.id}/`;
    const mem = make("span", "aihub-mem");
    const stop = make("button", "aihub-stop", "Stop");
    stop.type = "button";
    let sure = null; // a first tap asks "Stop it?"; it resets after a few seconds
    stop.addEventListener("click", async () => {
      if (!sure) {
        stop.textContent = "Stop it?";
        stop.classList.add("aihub-sure");
        sure = setTimeout(() => {
          sure = null;
          stop.textContent = "Stop";
          stop.classList.remove("aihub-sure");
        }, 5000);
        return;
      }
      clearTimeout(sure);
      stop.disabled = true;
      stop.textContent = "Stopping…";
      await fetch(`/hub/api/apps/${tool.id}/stop`, { method: "POST" }).catch(() => {});
      if (tool.id === here) location.href = "/";
      else load();
    });
    el.append(make("span", "aihub-dot"), name, mem, stop);
    return { el, mem };
  }

  let timer = null;
  async function load() {
    clearTimeout(timer);
    try {
      const data = await (await fetch("/hub/api/status", { cache: "no-store" })).json();
      // A tool counts as running when it holds a model (or is starting). Its page
      // alone is a small program (well under 1 GB) and isn't worth a chip.
      const live = data.apps.filter((t) => t.state === "starting" || (t.state === "running" && t.memory >= IN_USE));
      for (const id of chips.keys()) {
        if (!live.some((t) => t.id === id)) { chips.get(id).el.remove(); chips.delete(id); }
      }
      const parts = [home];
      for (const tool of live) {
        if (!chips.has(tool.id)) chips.set(tool.id, chip(tool));
        const c = chips.get(tool.id);
        c.el.className = `aihub-chip aihub-${tool.state}` + (tool.id === here ? " aihub-here" : "");
        c.mem.textContent = tool.state === "running" ? gb(tool.memory) : "starting…";
        parts.push(c.el);
      }
      if (!live.length) parts.push(none);
      mac.textContent = `Mac: ${gb(data.mac.used)} of ${gb(data.mac.total)}`;
      parts.push(mac);
      // Only re-order when something came or went (moving a node keeps it).
      if (parts.some((part, i) => bar.children[i] !== part) || bar.children.length !== parts.length) {
        bar.replaceChildren(...parts);
      }
      window.dispatchEvent(new CustomEvent("aihub-status", { detail: data }));
    } catch { /* the hub is restarting; try again shortly */ }
    timer = setTimeout(load, 3000);
  }
  load();
})();
