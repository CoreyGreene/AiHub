"""Run the server: python -m server --host 127.0.0.1 --port 8710

Normally started by AiHub (through start.py, which sets up .venv first).
"""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8710)
    args = parser.parse_args()
    print(f"\nLights AI is running on http://{args.host}:{args.port}\n  Stop with Ctrl+C\n", flush=True)
    uvicorn.run("server.app:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
