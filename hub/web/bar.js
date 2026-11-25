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
  // --- 🎤 next to every prompt box (every <textarea>, in every tool) ---
  // Tap to record, tap again to stop; Speech (Whisper, on this Mac) writes
  // what was said into the box, after anything already there. Browsers only
  // allow the mic on a secure page (https, or localhost on the Mac itself),
  // so elsewhere the button isn't added.
  if (window.isSecureContext && navigator.mediaDevices?.getUserMedia && window.MediaRecorder) {
    const micCss = document.createElement("style");
    micCss.textContent = `
      .aihub-mic-row { display: flex; justify-content: flex-end; margin-top: 6px; }
      .aihub-mic { font: 600 14px/1 system-ui, -apple-system, sans-serif; color: #ececf1; background: #20202a;
        border: 1px solid #34343f; border-radius: 999px; padding: 0 14px; min-height: 36px; cursor: pointer; }
      .aihub-mic:hover { border-color: #7c6cff; }
      .aihub-mic.aihub-rec { background: #d9534f; border-color: #d9534f; }
      .aihub-mic:disabled { opacity: 0.7; cursor: default; }
      .aihub-mic-note { color: #ff8a80; font: 13px system-ui, sans-serif; margin: 4px 0 0; text-align: right; }
    `;
    document.head.append(micCss);

    const addMic = (box) => {
      if (box.dataset.aihubMic) return;
      box.dataset.aihubMic = "1";
      const row = make("div", "aihub-mic-row");
      const btn = make("button", "aihub-mic", "🎤 Speak");
      btn.type = "button";
      const note = make("p", "aihub-mic-note");
      note.hidden = true;
      row.append(btn);
      box.after(row, note);
      let rec = null;

      btn.addEventListener("click", async () => {
        if (rec) return rec.stop(); // second tap: stop and write it down
        note.hidden = true;
        let stream;
        try {
          stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch {
          note.textContent = "The mic isn't allowed. Allow it for this page in the browser's settings.";
          note.hidden = false;
          return;
        }
        const parts = [];
        rec = new MediaRecorder(stream);
        rec.ondataavailable = (e) => e.data.size && parts.push(e.data);
        rec.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          const type = rec.mimeType || "audio/webm";
          rec = null;
          btn.classList.remove("aihub-rec");
          btn.disabled = true;
          btn.textContent = "Writing it down…";
          try {
            const res = await fetch("/hub/api/listen", { method: "POST", headers: { "Content-Type": type }, body: new Blob(parts, { type }) });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail);
            if (data.text) {
              const before = box.value.trimEnd();
              box.value = before ? `${before} ${data.text}` : data.text;
              box.dispatchEvent(new Event("input", { bubbles: true })); // the page sees the change
            } else {
              note.textContent = "Didn't catch any words. Try again a little closer to the mic.";
              note.hidden = false;
            }
          } catch (err) {
            note.textContent = err.message || "Couldn't reach Speech. Is the hub running?";
            note.hidden = false;
          }
          btn.disabled = false;
          btn.textContent = "🎤 Speak";
        };
        rec.start();
        btn.classList.add("aihub-rec");
        btn.textContent = "■ Stop";
      });
    };

    document.querySelectorAll("textarea").forEach(addMic);
    // Prompt boxes a page adds later (an Edit box, a new form) get one too.
    new MutationObserver(() => document.querySelectorAll("textarea:not([data-aihub-mic])").forEach(addMic))
      .observe(document.body, { childList: true, subtree: true });
  }
})();
