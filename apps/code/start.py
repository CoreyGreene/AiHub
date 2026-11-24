"""Start CodeAi.

    python3 start.py              # port 8200
    python3 start.py --port 9000  # another port

The first run makes a private Python environment in .venv and installs
what requirements.txt lists. Later runs reuse it (and update it when
requirements.txt changes). If this Python is too old (a Mac's built-in
python3 is 3.9), it looks for a newer one and starts again with that.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = VENV / "requirements.sha256"
NEWER = ["python3.13", "python3.12", "python3.11", "python3.10"]


def venv_python() -> Path:
    return VENV / "bin" / "python"


def use_newer_python() -> None:
    """Start again with a newer Python: .venv's if there is one, else the newest on this computer."""
    found = [str(venv_python())] if venv_python().exists() else []
    found += [p for p in map(shutil.which, NEWER) if p]
    if not found:
        sys.exit("CodeAi needs Python 3.10 or newer (this is %d.%d). On a Mac: brew install python@3.12" % sys.version_info[:2])
    os.execv(found[0], [found[0], __file__, *sys.argv[1:]])


def ensure_venv() -> None:
    wanted = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if STAMP.exists() and STAMP.read_text().strip() == wanted:
        return
    # uv reuses packages already downloaded for other projects (mlx is big), so prefer it when it's here.
    uv = shutil.which("uv")
    if not venv_python().exists():
        print("First run: making .venv ...")
        if uv:
            subprocess.check_call([uv, "venv", "-q", "--python", sys.executable, str(VENV)])
        else:
            venv.create(VENV, with_pip=True)
    print("Installing requirements ...")
    if uv:
        subprocess.check_call([uv, "pip", "install", "-q", "--python", str(venv_python()), "-r", str(REQUIREMENTS)])
    else:
        subprocess.check_call([str(venv_python()), "-m", "pip", "install", "-q", "-r", str(REQUIREMENTS)])
    STAMP.write_text(wanted)


def main() -> None:
    if sys.version_info < (3, 10):
        use_newer_python()

    parser = argparse.ArgumentParser(description="Start the CodeAi website.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("CODEAI_PORT", 8200)))
    parser.add_argument(
        "--host",
        default=os.environ.get("CODEAI_HOST", "0.0.0.0"),
        help="0.0.0.0 = reachable from other devices on the network (default)",
    )
    args = parser.parse_args()

    ensure_venv()
    cmd = [str(venv_python()), "-m", "server", "--host", args.host, "--port", str(args.port)]
    server = subprocess.Popen(cmd, cwd=ROOT)
    try:
        sys.exit(server.wait())
    except KeyboardInterrupt:
        # Ctrl+C reaches the server too: wait while it stops (and lets go of the model)
        print("\nStopping...")
        sys.exit(server.wait())


if __name__ == "__main__":
    main()
