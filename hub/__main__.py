"""Run the web server: python -m hub --host 0.0.0.0 --port 8000

Normally started through start.py, which sets up .venv first.
"""

import argparse
import os
import socket

import uvicorn


def lan_address() -> str | None:
    """Best guess at this computer's address on the local network."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no data is sent
            return s.getsockname()[0]
    except OSError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    print(f"\nAiHub is running.\n  On this computer: http://localhost:{args.port}")
    if args.host == "0.0.0.0" and (ip := lan_address()):
        print(f"  From your phone:  http://{ip}:{args.port}")
    print("  Stop with Ctrl+C (stops the tools too)\n", flush=True)
    os.environ["AIHUB_PORT"] = str(args.port)  # the tools it starts are told where it is (AIHUB_URL)
    uvicorn.run("hub.app:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
