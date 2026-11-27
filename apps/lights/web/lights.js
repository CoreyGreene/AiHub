// Lights AI page: a card for all the lights, then one per light. Changes go out when a slider is let go.
const $ = (sel, el = document) => el.querySelector(sel);
const PRESETS = [[2700, "Warm"], [3000, "3000"], [3500, "3500"], [4000, "4000"], [5000, "Day"]];
let cards = [];       // {el, kind: "all"|"light", target, home, light}
let shape = "";       // which lights the cards were made for
let quietUntil = 0;   // just after a change, don't let an older reading move the sliders back

async function call(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) } : {});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Lights AI answered ${r.status}`);
  return data;
}

function note(text) {
  const el = $("#note");
  el.textContent = text || "";
  el.hidden = !text;
}

async function send(card, change) {
  quietUntil = Date.now() + 2500;
  try {
    await call("api/set", { lights: card.target, ...change });
    note("");
    setTimeout(load, 1800);
  } catch (err) {
    note(err.message);
  }
}

function makeCard(kind, target, title, kMin, kMax, hasTemp) {
  const el = $("#card").content.firstElementChild.cloneNode(true);
  const card = { el, kind, target };
  if (kind === "all") el.classList.add("all");
  $(".name", el).textContent = title;

  const power = $(".power", el);
  power.onclick = () => {
    const on = !power.classList.contains("on");
    power.classList.toggle("on", on);
    power.classList.remove("mixed");
    el.classList.toggle("is-on", on);
    send(card, { on });
  };

  const b = $(".b", el), bOut = $(".b-out", el);
  b.value = 100;
  bOut.textContent = "";
  b.oninput = () => { bOut.textContent = `${b.value}%`; touching(b); };
  b.onchange = () => { send(card, { brightness: Number(b.value) }); b.dataset.touching = ""; };

  const k = $(".k", el), kOut = $(".k-out", el);
  k.min = kMin;
  k.max = kMax;
  k.value = 3000;
  k.oninput = () => { kOut.textContent = `${k.value} K`; touching(k); pick(card, Number(k.value)); };
  k.onchange = () => { send(card, { kelvin: Number(k.value) }); k.dataset.touching = ""; };

  const presets = $(".presets", el);
  for (const [kelvin, label] of PRESETS) {
    const p = document.createElement("button");
    p.className = "button small";
    p.type = "button";
    p.textContent = label;
    p.dataset.k = kelvin;
    p.onclick = () => { k.value = kelvin; kOut.textContent = `${kelvin} K`; pick(card, kelvin); send(card, { kelvin }); };
    presets.append(p);
  }
  if (!hasTemp) el.querySelectorAll(".temp").forEach((t) => (t.hidden = true));
  card.b = b; card.bOut = bOut; card.k = k; card.kOut = kOut; card.power = power;
  cards.push(card);
  return el;
}

function touching(input) {
  input.dataset.touching = "1";
  quietUntil = Date.now() + 2500;
}

function pick(card, kelvin) {
  card.el.querySelectorAll(".presets .button").forEach((p) => p.classList.toggle("picked", Number(p.dataset.k) === kelvin));
}

function build(data) {
  const box = $("#homes");
  box.replaceChildren();
  cards = [];
  const many = data.homes.length > 1;
  for (const home of data.homes) {
    if (many) box.append(Object.assign(document.createElement("h3"), { textContent: home.name }));
    const anyTemp = home.lights.some((l) => l.has_temp);
    box.append(makeCard("all", many ? `all of ${home.name}` : "all", "All lights", data.kelvin_min, data.kelvin_max, anyTemp));
    cards.at(-1).home = home.id;
    for (const light of home.lights) {
      box.append(makeCard("light", light.name, light.name, data.kelvin_min, data.kelvin_max, light.has_temp));
      Object.assign(cards.at(-1), { home: home.id, light: light.id });
    }
  }
}

function show(card, on, brightness, kelvin, stateText) {
  const quiet = Date.now() < quietUntil;
  card.el.querySelector(".state").textContent = stateText;
  card.el.classList.toggle("is-on", on === true || on === "mixed");
  if (quiet) return;
  card.power.classList.toggle("on", on === true);
  card.power.classList.toggle("mixed", on === "mixed");
  if (brightness && !card.b.dataset.touching && document.activeElement !== card.b) {
    card.b.value = brightness;
    card.bOut.textContent = `${brightness}%`;
  }
  if (kelvin && !card.k.dataset.touching && document.activeElement !== card.k) {
    card.k.value = kelvin;
    card.kOut.textContent = `${kelvin} K`;
    pick(card, kelvin);
  }
}

function describe(l) {
  if (l.on === null) return "No answer yet";
  if (!l.on) return "Off";
  return [`${l.brightness}%`, l.has_temp && l.kelvin ? `${l.kelvin} K` : ""].filter(Boolean).join(" · ");
}

function render(data) {
  const now = JSON.stringify(data.homes.map((h) => [h.id, h.lights.map((l) => l.id)]));
  if (now !== shape) { build(data); shape = now; }
  for (const card of cards) {
    const home = data.homes.find((h) => h.id === card.home);
    if (card.kind === "light") {
      const l = home.lights.find((x) => x.id === card.light);
      show(card, l.on, l.brightness, l.kelvin, describe(l));
    } else if (card.kind === "all") {
      const known = home.lights.filter((l) => l.on !== null), lit = known.filter((l) => l.on);
      const on = !lit.length ? false : lit.length === home.lights.length ? true : "mixed";
      const avg = lit.length ? Math.round(lit.reduce((s, l) => s + l.brightness, 0) / lit.length) : 0;
      const ks = [...new Set(lit.map((l) => l.kelvin).filter(Boolean))];
      show(card, on, avg, ks.length === 1 ? ks[0] : 0, `${lit.length} of ${home.lights.length} on`);
    }
  }
}

const WAITING_NOTE = $("#loading-note").textContent;

function loading(title, text, problem = false) {
  $("#loading").hidden = false;
  $("#homes").hidden = true;
  $("#status").hidden = true;
  $("#loading h2").textContent = title;
  $("#loading-note").textContent = text;
  $("#loading").classList.toggle("problem", problem);
}

function status(text) {
  $("#status").textContent = text || "";
  $("#status").hidden = !text;
}

async function load() {
  let data;
  try {
    data = await call("api/lights");
  } catch (err) {
    if (!shape) loading("Starting Lights AI…", WAITING_NOTE);  // the hub answers 503 until it's up
    else { status(`Lights AI isn't answering (${err.message}).`); $("#homes").classList.add("offline"); }
    return;
  }
  if (!data.ready) {
    loading("No lights saved yet", "In apps/lights, run:  .venv/bin/python halo.py login", true);
    return;
  }
  // Until a light has answered we know nothing, so show no cards (they'd say "off", which may not be true).
  const heard = data.homes.some((h) => h.lights.some((l) => l.on !== null));
  const notes = data.homes.map((h) => h.note).filter(Boolean).join(" ");
  if (!heard) {
    loading("Connecting to your lights…", notes ? `Still trying. ${notes}` : WAITING_NOTE);
    return;
  }
  $("#loading").hidden = true;
  $("#homes").hidden = false;
  const lost = data.homes.filter((h) => !h.connected);
  $("#homes").classList.toggle("offline", lost.length > 0);
  status(lost.map((h) => `Reconnecting to ${h.name}…${h.note ? " " + h.note : ""}`).join(" "));
  render(data);
}

$("#refresh").onclick = async () => {
  try { await call("api/refresh", {}); } catch (err) { note(err.message); }
  setTimeout(load, 1500);
};
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
load();
setInterval(() => { if (!document.hidden) load(); }, 4000);
