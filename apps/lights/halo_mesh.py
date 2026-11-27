"""The HALO Home (Avi-on CSRMesh) Bluetooth side of Lights AI, shared by halo.py (the command line) and the server.

- The saved file (lights.local.json): each home's mesh key, lights and groups, from `halo.py login`.
- Mesh messages: building them and reading the lights' answers (format from avionmesh, LGPL).
- Link: one Bluetooth connection into one home's mesh, through whichever light answers.
"""

import asyncio
import json
import os
import re
import warnings
from pathlib import Path

# recsrmesh uses an older import path in cryptography; harmless, but noisy.
warnings.filterwarnings("ignore", message=".*OFB has been moved.*")

HERE = Path(__file__).resolve().parent
SAVED = HERE / "lights.local.json"

# The CSRMesh service and its two characteristics (a packet is split across them).
SERVICE_UUID = "c4edc000-9daf-11e3-8000-00025b000b00"
CHAR_LOW = "c4edc000-9daf-11e3-8003-00025b000b00"
# What the lights put in their adverts: Avi-on lights send CSR's short id FEF1 (name "Avi-on").
ADVERT_UUIDS = {SERVICE_UUID, "0000fef1-0000-1000-8000-00805f9b34fb"}

MODEL_OPCODE = 0x73
VERB_WRITE, VERB_READ = 0, 1
NOUN_DIMMING, NOUN_COLOR = 10, 29
FIRST_DEVICE_ID = 32896  # ids below this are groups; 0 = the whole mesh

KELVIN_MIN, KELVIN_MAX = 2700, 5000  # what HALO Home lights do (warm to daylight)

PRODUCTS = {
    90: "Lamp Dimmer", 93: "Recessed Downlight (RL)", 94: "Light Adapter", 97: "Smart Dimmer",
    134: "Smart Bulb (A19)", 137: "Surface Downlight (BLD)", 162: "MicroEdge (HLB)", 167: "Smart Switch",
}
HAS_TEMP = {93, 134, 137, 162}  # products with a colour temperature


# ---------- saved file ----------

def load() -> dict | None:
    return json.loads(SAVED.read_text()) if SAVED.exists() else None


def save(data: dict):
    SAVED.write_text(json.dumps(data, indent=2))
    os.chmod(SAVED, 0o600)


# ---------- names ----------

ALL_WORDS = {"all", "everything", "every", "all lights", "every light", "everywhere", "whole house", "house", "home"}
_FILLER = {"the", "light", "lights", "lamp", "lamps", "my", "in", "room"}


def _norm(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", re.sub(r"['’]", "", name.lower())).split()
    kept = [w for w in words if w not in _FILLER]
    return " ".join(kept or words)


def find(data: dict, name: str) -> list[tuple[dict, int, str]]:
    """[(home, id, label)] for a light's name, a group's name or "all". Loose: "the fireplace", "PC lights" work.
    Raises ValueError with the names there are when nothing (or too much) fits."""
    raw = name.strip().lower()
    if raw in ALL_WORDS or _norm(name) in ALL_WORDS or not raw:
        return [(loc, 0, "All lights" if len(data["locations"]) == 1 else f"All of {loc['name']}")
                for loc in data["locations"]]
    for prefix in ("all of ", "all lights in ", "all "):  # "all of Home": one home's lights, when there are several
        if raw.startswith(prefix):
            homes = [loc for loc in data["locations"] if _norm(loc["name"]) == _norm(raw[len(prefix):])]
            if homes:
                return [(loc, 0, f"All of {loc['name']}") for loc in homes]
    want = _norm(name)
    exact, partial = [], []
    for loc in data["locations"]:
        for items in (loc["devices"], loc["groups"]):
            for it in items:
                have = _norm(it["name"])
                hit = (loc, it["avid"], it["name"])
                if have == want or it["name"].lower() == raw:
                    exact.append(hit)
                elif want in have or have in want:
                    partial.append(hit)
    hits = exact or partial
    if not hits:
        raise ValueError(f"There's no light called {name}. {everything(data)}")
    if len(hits) > 1 and not exact:
        raise ValueError(f"{name} could be " + " or ".join(h[2] for h in hits) + ".")
    return hits


def everything(data: dict) -> str:
    lights = [d["name"] for loc in data["locations"] for d in loc["devices"]]
    groups = [g["name"] for loc in data["locations"] for g in loc["groups"]]
    out = "The lights: " + ", ".join(lights) + "."
    return out + (" The groups: " + ", ".join(groups) + "." if groups else "")


# ---------- mesh messages ----------

def packet(target: int, verb: int, noun: int, value: bytes) -> tuple[int, bytes]:
    group, dest = (target, 0) if target < FIRST_DEVICE_ID else (0, target)
    return dest, bytes([verb, noun, group >> 8, group & 0xFF, 0, *value, 0, 0])


def brightness_value(level: int) -> bytes:
    return bytes([max(0, min(255, level)), 0, 0])


def kelvin_value(kelvin: int) -> bytes:
    k = max(KELVIN_MIN, min(KELVIN_MAX, kelvin))
    return bytes([0x01, k >> 8, k & 0xFF])


def parse(resp: dict) -> dict | None:
    """A light's answer: {'avid', 'brightness' (0-255)} or {'avid', 'kelvin'}."""
    if resp.get("opcode") != MODEL_OPCODE:
        return None
    data = resp["payload"]
    if len(data) < 4 or (data[0] == 0 and data[1] == 0):
        return None
    avid = resp["crypto_source"] if resp["source"] == 0x8000 else resp["source"]
    if data[0] == VERB_WRITE:
        avid = avid or int.from_bytes(data[2:4], "big")
        value = data[4:]
    else:
        value = data[2:]
    if data[1] == NOUN_DIMMING and len(value) >= 2:
        return {"avid": avid, "brightness": value[1]}
    if data[1] == NOUN_COLOR and len(value) >= 4:
        k = int.from_bytes(value[2:4], "big")
        return {"avid": avid, "kelvin": k} if 1500 <= k <= 10000 else None
    return None


# ---------- Bluetooth ----------

async def scan(timeout: float = 6.0):
    """Mesh lights the Mac can hear, strongest first: ([(address, name, rssi, BLEDevice)], everything heard)."""
    from bleak import BleakScanner
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)

    def is_light(dev, adv) -> bool:
        uuids = {u.lower() for u in adv.service_uuids}
        name = (adv.local_name or dev.name or "").lower()
        return bool(uuids & ADVERT_UUIDS) or name.startswith("avi-on")

    mesh = [(addr, adv.local_name or dev.name or "?", adv.rssi, dev)
            for addr, (dev, adv) in found.items() if is_light(dev, adv)]
    return sorted(mesh, key=lambda m: m[2], reverse=True), found


async def ask_all(mesh, seconds: float = 3.0) -> list[dict]:
    """Ask every light how bright it is; their answers (only our own mesh can read the question)."""
    dest, payload = packet(0, VERB_READ, NOUN_DIMMING, bytes(3))
    await mesh.send(dest, MODEL_OPCODE, payload)
    return [p for p in (parse(r) for r in await mesh.receive(timeout=seconds)) if p]


class Link:
    """One Bluetooth connection into one home's mesh."""

    def __init__(self, loc: dict, say=print):
        self.loc, self.say = loc, say
        self.client, self.mesh, self.first_replies = None, None, []

    @property
    def connected(self) -> bool:
        return bool(self.client and self.client.is_connected)

    async def open(self, lights=None):
        from bleak import BleakClient
        from recsrmesh import CSRMesh
        if lights is None:
            lights, _ = await scan()
        candidates = [(m[0], m[3]) for m in lights]
        cached = self.loc.get("ble_address")
        candidates.sort(key=lambda c: c[0] != cached)  # the last light that worked first
        for addr, dev in candidates:
            client = BleakClient(dev, timeout=15)
            try:
                await client.connect()
                if client.services.get_characteristic(CHAR_LOW) is None:
                    raise RuntimeError("not a mesh light")
                mesh = CSRMesh(client, self.loc["passphrase"])
                await mesh.__aenter__()
                replies = await ask_all(mesh)
                if replies:  # answers mean this light is in our mesh
                    self.client, self.mesh, self.first_replies = client, mesh, replies
                    self.loc["ble_address"] = addr
                    return self
                self.say(f"  {addr[:8]}…  connected, but no light answered (another home's mesh?)")
                await mesh.__aexit__()
            except Exception as e:
                self.say(f"  {addr[:8]}…  skipped: {e}")
            try:
                await client.disconnect()
            except Exception:
                pass
        raise RuntimeError(f"Couldn't reach {self.loc['name']} over Bluetooth.")

    async def write(self, target: int, noun: int, value: bytes):
        dest, payload = packet(target, VERB_WRITE, noun, value)
        await self.mesh.send(dest, MODEL_OPCODE, payload)

    async def read_all(self):
        """Ask every light for its brightness and colour; the answers arrive through recv()."""
        for noun in (NOUN_DIMMING, NOUN_COLOR):
            dest, payload = packet(0, VERB_READ, noun, bytes(3))
            await self.mesh.send(dest, MODEL_OPCODE, payload)
            await asyncio.sleep(0.3)

    async def close(self):
        try:
            if self.mesh:
                await self.mesh.__aexit__()
        finally:
            if self.client:
                await self.client.disconnect()
