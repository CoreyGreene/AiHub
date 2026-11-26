"""Set up and run Sound AI, on its own or through AiHub."""

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = VENV / "requirements.sha256"


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Sound AI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8610)
    args = parser.parse_args()

    python = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        venv.create(VENV, with_pip=True)
    wanted = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if not STAMP.is_file() or STAMP.read_text().strip() != wanted:
        subprocess.check_call([str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
        STAMP.write_text(wanted + "\n")
    os.chdir(ROOT)
    os.execv(str(python), [str(python), "-m", "uvicorn", "app:app", "--host", args.host, "--port", str(args.port)])


if __name__ == "__main__":
    main()
