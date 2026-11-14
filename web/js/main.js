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
  const name = location.hash.slice(1) || "create";
  const view = document.getElementById(`view-${name}`) ? name : "create";
  document.querySelectorAll(".view").forEach((el) => (el.hidden = el.id !== `view-${view}`));
  document.querySelectorAll("[data-view]").forEach((el) => {
    if (el.dataset.view === view) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  onShow[view]?.();
}

window.addEventListener("hashchange", showView);
showView();
loadThemes();
