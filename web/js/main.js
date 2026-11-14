// The page only shows things and talks to the server.
// All image work happens on the server (server/generation.py).

import { startGpu } from "./gpu.js";
import { loadThemes } from "./theme-picker.js";
import { fillCustom } from "./custom.js";
import "./create.js";
import "./character-picker.js";
import { loadLibrary } from "./library.js";
import { loadSettings } from "./settings.js";
import { startQueueList } from "./queue-list.js";
import { loadThemeInfo } from "./theme-info.js";

// Tabs: Create, Library, Theme, and the Settings gear. The address ends in
// #create, #library and so on, so the phone's Back button works too.
// #library/<folder> opens one character, #library/<folder>/<date> one day of it.
const onShow = {
  library: loadLibrary,
  theme: loadThemeInfo,
  settings: () => {
    loadSettings();
    startQueueList();
  },
};

function showView() {
  // "#create/advanced" = the Create tab, its Advanced sub-tab.
  const [name, sub, more] = location.hash.slice(1).split("/");
  const view = document.getElementById(`view-${name}`) ? name : "create";
  document.querySelectorAll(".view").forEach((el) => (el.hidden = el.id !== `view-${view}`));
  document.querySelectorAll("[data-view]").forEach((el) => {
    if (el.dataset.view === view) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  if (view === "create") showCreateMode(["advanced", "custom"].includes(sub) ? sub : "standard");
  onShow[view]?.(sub, more);
}

// Inside Create: Standard, Advanced and Custom share one form. Advanced adds
// "How many pictures" and the options, and shows the results as a grid to
// pick from; Custom adds those but has no theme: you make your own.
function showCreateMode(mode) {
  document.getElementById("view-create").dataset.mode = mode;
  if (mode === "custom") fillCustom();
  document.querySelectorAll("[data-subview]").forEach((el) => {
    if (el.dataset.subview === mode) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
}

window.addEventListener("hashchange", showView);
showView();
loadThemes();
startGpu();
