"""Run the server: python -m server --host 127.0.0.1 --port 8500

Normally started by AiHub (through start.py, which sets up .venv first).
"""

import argparse
import os

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ["HF_HUB_OFFLINE"] = "1"  # the model is a local folder; never download

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8500)
    args = parser.parse_args()
    print(f"\nTalk is running on http://{args.host}:{args.port}\n  Stop with Ctrl+C\n", flush=True)
    uvicorn.run("server.app:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
