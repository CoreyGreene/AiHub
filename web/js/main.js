// The page only shows things and talks to the server.
// All image work happens on the server (server/generation.py).

import { loadThemes } from "./theme-picker.js";
import "./create.js";
import { loadLibrary } from "./library.js";
import { loadSettings } from "./settings.js";
import { loadThemeInfo } from "./theme-info.js";

// Tabs: Create, Library, Theme, and the Settings gear. The address ends in
// #create, #library and so on, so the phone's Back button works too.
const onShow = { library: loadLibrary, theme: loadThemeInfo, settings: loadSettings };

function showView() {
  // "#create/advanced" = the Create tab, its Advanced sub-tab.
  const [name, sub] = location.hash.slice(1).split("/");
  const view = document.getElementById(`view-${name}`) ? name : "create";
  document.querySelectorAll(".view").forEach((el) => (el.hidden = el.id !== `view-${view}`));
  document.querySelectorAll("[data-view]").forEach((el) => {
    if (el.dataset.view === view) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  if (view === "create") showCreateMode(sub === "advanced" ? "advanced" : "standard");
  onShow[view]?.();
}

// Inside Create: Standard and Advanced share one form; Advanced adds
// "How many pictures" and shows the results as a grid to pick from.
function showCreateMode(mode) {
  document.getElementById("view-create").dataset.mode = mode;
  document.querySelectorAll("[data-subview]").forEach((el) => {
    if (el.dataset.subview === mode) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
}

window.addEventListener("hashchange", showView);
showView();
loadThemes();
