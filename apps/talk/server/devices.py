"""Which microphone and speakers Always listening uses: by name, from the settings (mic, speakers; "" = the Mac's
default). By name, so plugging in headphones doesn't move Talk onto them; a device that isn't there falls back to
the default (and says so).

The audio library reads the list of devices once; refresh() reads it again (after something is plugged in or out).
Only call it with no stream open.
"""

from . import settings


def refresh() -> None:
    import sounddevice as sd

    try:
        sd._terminate()
        sd._initialize()
    except Exception:  # the list stays as it was
        pass


def listing() -> dict:
    """{inputs: [names], outputs: [names]}, each once, in the system's order."""
    import sounddevice as sd

    ins, outs = [], []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0 and d["name"] not in ins:
            ins.append(d["name"])
        if d["max_output_channels"] > 0 and d["name"] not in outs:
            outs.append(d["name"])
    return {"inputs": ins, "outputs": outs}


def pick(kind: str) -> tuple[int | None, str]:
    """(device index or None for the default, a note when the chosen one isn't there). kind: "input" or "output"."""
    import sounddevice as sd

    want = settings.get().get("mic" if kind == "input" else "speakers") or ""
    if not want:
        return None, ""
    channels = "max_input_channels" if kind == "input" else "max_output_channels"
    for i, d in enumerate(sd.query_devices()):
        if d["name"] == want and d[channels] > 0:
            return i, ""
    what = "microphone" if kind == "input" else "speakers"
    return None, f"The {what} picked ({want}) isn't connected: using the Mac's default for now."
