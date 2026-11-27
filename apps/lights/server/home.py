"""Keeps Lights AI connected to each home's mesh, and knows how each light is.

One Place per home in lights.local.json: it finds a light of its own mesh, stays connected, listens to what the
lights say (so a change from the wall or the HALO app shows up too), reconnects when the link drops, and asks
everyone how they are every few minutes.
"""

import asyncio
import logging
import re
import time

import halo_mesh as hm

log = logging.getLogger("lights")
POLL_SECONDS = 300
WAIT_FOR_LINK = 25  # how long a command waits for the link while it (re)connects


def percent(level: int) -> int:
    return round(level * 100 / 255)


def level_of(pct: float) -> int:
    pct = max(0.0, min(100.0, float(pct)))
    return 0 if pct == 0 else max(1, round(pct * 255 / 100))


class Place:
    def __init__(self, home: "Home", loc: dict):
        self.home, self.loc = home, loc
        self.link: hm.Link | None = None
        self.note = ""  # the last problem, said plainly
        self.state = {d["avid"]: {} for d in loc["devices"]}  # id -> {"brightness": 0-255, "kelvin": K}
        self.last_on: dict[int, int] = {}  # id -> its last brightness above 0, for "turn it back on"
        self.lock = asyncio.Lock()  # one write at a time
        self.up = asyncio.Event()
        self._refresh: asyncio.Task | None = None

    @property
    def devices(self) -> list[int]:
        return [d["avid"] for d in self.loc["devices"]]

    async def keep(self):
        delay = 5
        while True:
            link = None
            try:
                lights, _ = await hm.scan()
                before = self.loc.get("ble_address")
                link = await hm.Link(self.loc, say=log.info).open(lights)
                if self.loc.get("ble_address") != before:
                    self.home.save()
                self.link, self.note, delay = link, "", 5
                self.up.set()
                log.info(f"{self.loc['name']}: connected")
                for r in link.first_replies:
                    self.absorb(r)
                async with self.lock:
                    await link.read_all()
                polled = time.monotonic()
                while link.connected:
                    resp = await link.mesh.recv(timeout=1.0)
                    if resp and (p := hm.parse(resp)):
                        self.absorb(p)
                    if time.monotonic() - polled > POLL_SECONDS:
                        async with self.lock:
                            await link.read_all()
                        polled = time.monotonic()
                self.note = "The Bluetooth connection dropped."
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.note = str(e) or e.__class__.__name__
                log.warning(f"{self.loc['name']}: {self.note}")
            finally:
                self.up.clear()
                self.link = None
                if link:
                    try:
                        await link.close()
                    except Exception:
                        pass
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    def absorb(self, p: dict):
        avid = p["avid"]
        if avid not in self.state:  # 0 (our own question echoing back) or a light we don't know
            return
        if "brightness" in p:
            self.state[avid]["brightness"] = p["brightness"]
            if p["brightness"] > 0:
                self.last_on[avid] = p["brightness"]
        if "kelvin" in p:
            self.state[avid]["kelvin"] = p["kelvin"]

    def guess(self, avid: int, level: int | None, kelvin: int | None):
        """What a write should have done, until the lights say so themselves."""
        ids = self.devices if avid == 0 else [avid] if avid in self.state else []
        for i in ids:
            if level is not None:
                self.state[i]["brightness"] = level
                if level > 0:
                    self.last_on[i] = level
            if kelvin is not None:
                self.state[i]["kelvin"] = max(hm.KELVIN_MIN, min(hm.KELVIN_MAX, kelvin))

    def refresh_soon(self):
        """Ask everyone how they are shortly after a change (groups: we don't know who's in them)."""
        async def later():
            await asyncio.sleep(1.5)
            if self.link:
                async with self.lock:
                    await self.link.read_all()
        if self._refresh and not self._refresh.done():
            self._refresh.cancel()
        self._refresh = asyncio.create_task(later())

    async def ready(self) -> hm.Link:
        if not self.up.is_set():
            try:
                await asyncio.wait_for(self.up.wait(), WAIT_FOR_LINK)
            except TimeoutError:
                raise RuntimeError(f"Lights AI can't reach {self.loc['name']} right now. {self.note}".strip())
        return self.link

    def view(self) -> dict:
        lights = []
        for d in self.loc["devices"]:
            s = self.state.get(d["avid"], {})
            b = s.get("brightness")
            lights.append({
                "id": d["avid"], "name": d["name"], "product": d.get("product"),
                "has_temp": d.get("product_id") in hm.HAS_TEMP,
                "on": None if b is None else b > 0,
                "brightness": None if b is None else percent(b),
                "kelvin": s.get("kelvin"),
            })
        return {"id": self.loc["id"], "name": self.loc["name"],
                "connected": self.up.is_set(), "note": self.note,
                "lights": lights, "groups": [{"id": g["avid"], "name": g["name"]} for g in self.loc["groups"]]}


def split_names(lights) -> list[str]:
    """["fireplace", "stair"], or "fireplace and stair", or "fireplace, stair" -> names."""
    items = [lights] if isinstance(lights, str) else list(lights or [])
    out = []
    for item in items:
        out += [p.strip() for p in re.split(r",|\band\b|&", str(item)) if p.strip()]
    return out or ["all"]


class Home:
    def __init__(self):
        self.data = hm.load()
        self.places = {loc["id"]: Place(self, loc) for loc in (self.data or {}).get("locations", [])}
        self.tasks: list[asyncio.Task] = []

    def start(self):
        self.tasks = [asyncio.create_task(p.keep()) for p in self.places.values()]

    async def stop(self):
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    def save(self):
        hm.save(self.data)

    def view(self) -> dict:
        return {"ready": bool(self.places), "kelvin_min": hm.KELVIN_MIN, "kelvin_max": hm.KELVIN_MAX,
                "homes": [p.view() for p in self.places.values()]}

    async def set(self, lights, on: bool | None = None, brightness: float | None = None,
                  kelvin: int | None = None) -> dict:
        """Do it to the lights named: on/off, a brightness (0-100 %), a colour temperature (K). Any mix."""
        if not self.places:
            raise ValueError("No lights are saved yet. Run  python halo.py login  in apps/lights first.")
        if on is None and brightness is None and kelvin is None:
            raise ValueError("Say what to do: on, off, a brightness or a colour temperature.")
        hits, seen = [], set()
        for name in split_names(lights):
            for loc, avid, label in hm.find(self.data, name):  # ValueError: no such light (names it gives)
                if (loc["id"], avid) not in seen:
                    seen.add((loc["id"], avid))
                    hits.append((self.places[loc["id"]], avid, label))

        if on is False or brightness == 0:
            level, said = 0, "off"
        elif brightness is not None:
            level, said = level_of(brightness), f"{round(min(100, max(0, brightness)))}%"
        elif on:
            level, said = None, "on"  # each light back to how bright it was (or full)
        else:
            level, said = None, ""
        if kelvin is not None:
            kelvin = max(hm.KELVIN_MIN, min(hm.KELVIN_MAX, int(kelvin)))
            said = ", ".join(x for x in (said, f"{kelvin} K") if x)

        done = []
        for place, avid, label in hits:
            link = await place.ready()
            # "on" with no brightness: a single light (or each light, for all) goes back to its last brightness.
            singles = place.devices if (avid == 0 and on and level is None) else [avid]
            async with place.lock:
                for target in singles:
                    if kelvin is not None:
                        await link.write(target, hm.NOUN_COLOR, hm.kelvin_value(kelvin))
                    lv = level
                    if lv is None and on:
                        lv = place.last_on.get(target, 255) if target >= hm.FIRST_DEVICE_ID else 255
                    if lv is not None:
                        await link.write(target, hm.NOUN_DIMMING, hm.brightness_value(lv))
                    place.guess(target, lv, kelvin)
                    await asyncio.sleep(0.15)  # don't flood the mesh
            place.refresh_soon()
            done.append(label)
        return {"done": done, "message": f"{' and '.join(done)}: {said}."}

    async def refresh(self):
        for p in self.places.values():
            if p.link:
                async with p.lock:
                    await p.link.read_all()
