"""Start AiHub: one website for all the AI tools.

    python3 start.py              # port 8000
    python3 start.py --port 9000  # another port

The tools themselves (apps/*) start when you open their tile.

The first run makes a private Python environment in .venv and installs
what requirements.txt lists. Later runs reuse it (and update it when
requirements.txt changes). Works the same on Linux and macOS.
"""

import argparse
import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = VENV / "requirements.sha256"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def ensure_venv() -> None:
    if not venv_python().exists():
        print("First run: making .venv ...")
        venv.create(VENV, with_pip=True)

    wanted = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if STAMP.exists() and STAMP.read_text().strip() == wanted:
        return
    print("Installing requirements ...")
    subprocess.check_call([str(venv_python()), "-m", "pip", "install", "-q", "-r", str(REQUIREMENTS)])
    STAMP.write_text(wanted)


def main() -> None:
    if sys.version_info < (3, 10):
        sys.exit("AiHub needs Python 3.10 or newer (this is %d.%d)." % sys.version_info[:2])

    parser = argparse.ArgumentParser(description="Start the AiHub website.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("AIHUB_PORT", 8000)))
    parser.add_argument(
        "--host",
        default=os.environ.get("AIHUB_HOST", "0.0.0.0"),
        help="0.0.0.0 = reachable from other devices on the network (default)",
    )
    args = parser.parse_args()

    ensure_venv()
    cmd = [str(venv_python()), "-m", "hub", "--host", args.host, "--port", str(args.port)]
    sys.exit(subprocess.call(cmd, cwd=ROOT))


if __name__ == "__main__":
    main()
