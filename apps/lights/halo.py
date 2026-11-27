#!/usr/bin/env python3
"""Halo lights from the command line (Lights AI's setup and test tool).

    python halo.py login            # once per HALO Home account: save the mesh key + light list
    python halo.py list             # what was saved (no Bluetooth)
    python halo.py scan [--all]     # which mesh lights the Mac can hear (--all: every device, all it advertises)
    python halo.py status           # connect, ask every light how bright it is
    python halo.py on  <light|group|all>
    python halo.py off <light|group|all>
    python halo.py dim <light|group|all> <percent>
    python halo.py temp <light|group|all> <kelvin>

The cloud is used only by `login`. Everything else is local Bluetooth. The password is never saved;
lights.local.json holds the mesh key, so it's private (chmod 600, not in git).
While Lights AI runs it holds the connection: these commands may then have to use another light, or wait.
"""

import argparse
import asyncio
import getpass
import json
import sys
import urllib.error
import urllib.request

import halo_mesh as hm

API = "https://api.avi-on.com/"


def need() -> dict:
    data = hm.load()
    if not data:
        sys.exit("No lights saved yet. Run:  python halo.py login")
    return data


# ---------- cloud (login only) ----------

def api(path: str, body: dict | None = None, token: str | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Accept", "application/api.avi-on.v3")
        req.add_header("Authorization", f"Token {token}")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def cmd_login(_args):
    print("Sign in with your HALO Home account. The password is used once and not saved.")
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")
    try:
        resp = api("sessions", {"email": email, "password": password})
    except urllib.error.HTTPError as e:
        sys.exit(f"Sign-in failed ({e.code}). Check the email and password.")
    token = (resp.get("credentials") or {}).get("auth_token")
    if not token:
        sys.exit("Sign-in failed: no token came back.")

    old = {loc["id"]: loc for loc in (hm.load() or {"locations": []})["locations"]}
    for raw in api("user/locations", token=token)["locations"]:
        pid = raw["pid"]
        loc = api(f"locations/{pid}", token=token)["location"]
        devices = [
            {"avid": d["avid"], "name": d["name"], "product_id": d.get("product_id"),
             "product": hm.PRODUCTS.get(d.get("product_id"), "Unknown"), "mac": d.get("friendly_mac_address")}
            for d in api(f"locations/{pid}/abstract_devices", token=token)["abstract_devices"]
            if d.get("type") == "device"
        ]
        groups = [{"avid": g["avid"], "name": g["name"]}
                  for g in api(f"locations/{pid}/groups", token=token)["groups"]]
        old[pid] = {
            "id": pid, "name": loc.get("name") or f"Location {pid}", "account": email,
            "passphrase": loc["passphrase"], "ble_address": old.get(pid, {}).get("ble_address"),
            "devices": devices, "groups": groups,
        }
    hm.save({"locations": list(old.values())})
    print(f"Saved to {hm.SAVED.name}:")
    cmd_list(None)


def cmd_list(_args):
    for loc in need()["locations"]:
        print(f"\n{loc['name']}  ({loc['account']})")
        for d in loc["devices"]:
            print(f"  light  {d['name']:<24} id {d['avid']:<6} {d['product']}")
        for g in loc["groups"]:
            print(f"  group  {g['name']:<24} id {g['avid']}")


# ---------- Bluetooth ----------

async def cmd_scan(args):
    lights, found = await hm.scan()
    if args.all:
        for addr, (dev, adv) in sorted(found.items(), key=lambda f: f[1][1].rssi, reverse=True):
            print(f"\n{adv.local_name or dev.name or '(no name)'}  signal {adv.rssi} dBm  {addr}")
            for u in adv.service_uuids:
                print(f"    service  {u}")
            for k, v in adv.manufacturer_data.items():
                print(f"    maker    0x{k:04x}  {bytes(v).hex()}")
            for k, v in adv.service_data.items():
                print(f"    data     {k}  {bytes(v).hex()}")
        print()
    print(f"Heard {len(found)} Bluetooth devices; {len(lights)} are mesh lights:")
    for addr, name, rssi, _ in lights:
        print(f"  {name:<20} signal {rssi:>4} dBm   {addr}")
    if not lights:
        print("None found. Is Bluetooth on, and does this terminal app have Bluetooth permission?")


async def cmd_status(_args):
    data = need()
    lights, _ = await hm.scan()
    for loc in data["locations"]:
        print(f"\n{loc['name']}: connecting…")
        try:
            link = await hm.Link(loc).open(lights)
        except RuntimeError as e:
            print(f"  {e}")
            continue
        seen = {}
        for r in link.first_replies:
            seen.setdefault(r["avid"], {}).update(r)
        await link.close()
        label = {d["avid"]: d["name"] for d in loc["devices"]}
        for avid, name in label.items():
            r = seen.get(avid)
            if r and "brightness" in r:
                pct = round(r["brightness"] * 100 / 255)
                print(f"  {name:<24} {'off' if pct == 0 else f'{pct}%'}")
            else:
                print(f"  {name:<24} no answer")
        for avid in seen.keys() - label.keys() - {0}:  # 0 is our own question echoing back
            print(f"  (unknown light id {avid}) {seen[avid]}")
    hm.save(data)


async def run_write(target_name: str, noun: int, value: bytes, said: str):
    data = need()
    try:
        hits = hm.find(data, target_name)
    except ValueError as e:
        sys.exit(str(e))
    lights, _ = await hm.scan()
    for loc in {id(h[0]): h[0] for h in hits}.values():
        try:
            link = await hm.Link(loc).open(lights)
        except RuntimeError as e:
            print(e)
            continue
        for hloc, avid, label in hits:
            if hloc is loc:
                await link.write(avid, noun, value)
                print(f"{label}: {said}")
        await asyncio.sleep(0.4)  # let it go out before we hang up
        await link.close()
    hm.save(data)


async def cmd_on(a):
    await run_write(a.target, hm.NOUN_DIMMING, hm.brightness_value(255), "on")


async def cmd_off(a):
    await run_write(a.target, hm.NOUN_DIMMING, hm.brightness_value(0), "off")


async def cmd_dim(a):
    pct = max(0, min(100, a.percent))
    level = 0 if pct == 0 else max(1, round(pct * 255 / 100))
    await run_write(a.target, hm.NOUN_DIMMING, hm.brightness_value(level), f"{pct}%")


async def cmd_temp(a):
    k = max(hm.KELVIN_MIN, min(hm.KELVIN_MAX, a.kelvin))
    await run_write(a.target, hm.NOUN_COLOR, hm.kelvin_value(k), f"{k} K")


def main():
    p = argparse.ArgumentParser(description="Control HALO Home lights over Bluetooth.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login").set_defaults(fn=cmd_login)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("scan")
    s.add_argument("--all", action="store_true", help="show everything every device advertises")
    s.set_defaults(fn=cmd_scan)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    for name, fn in (("on", cmd_on), ("off", cmd_off)):
        s = sub.add_parser(name)
        s.add_argument("target")
        s.set_defaults(fn=fn)
    s = sub.add_parser("dim")
    s.add_argument("target")
    s.add_argument("percent", type=int)
    s.set_defaults(fn=cmd_dim)
    s = sub.add_parser("temp")
    s.add_argument("target")
    s.add_argument("kelvin", type=int)
    s.set_defaults(fn=cmd_temp)
    args = p.parse_args()
    result = args.fn(args)
    if asyncio.iscoroutine(result):
        asyncio.run(result)


if __name__ == "__main__":
    main()
