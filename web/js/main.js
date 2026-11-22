// The page only shows things and talks to the server; the models run on the server.

import { startStatus } from "./status.js";
import { loadModels, showAsk } from "./ask.js";
import { loadHistory } from "./history.js";
import { loadSettings } from "./settings.js";

// Tabs: Ask, History, and the Settings gear. The address ends in #ask, #history and so on, so the phone's Back
// button works too. #ask/<conversation> opens one conversation in Ask.
const onShow = {
  ask: (sub) => showAsk(sub),
  history: loadHistory,
  settings: loadSettings,
};

function showView() {
  const [name, sub] = location.hash.slice(1).split("/");
  const view = document.getElementById(`view-${name}`) ? name : "ask";
  document.querySelectorAll(".view").forEach((el) => (el.hidden = el.id !== `view-${view}`));
  document.querySelectorAll("[data-view]").forEach((el) => {
    if (el.dataset.view === view) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  onShow[view]?.(sub);
}

window.addEventListener("hashchange", showView);
startStatus();
loadModels().then(showView);
