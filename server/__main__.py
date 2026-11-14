"""Run the web server: python -m server --host 0.0.0.0 --port 8100

Normally started through start.py, which sets up .venv first.
"""

import argparse
import os
import socket

# Let PyTorch reuse graphics memory more flexibly (fewer out-of-memory errors
# on NVIDIA cards; ignored elsewhere), and keep library chatter out of the log.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("DIFFUSERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

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
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()

    print(f"\nImageAi is running.\n  On this computer: http://localhost:{args.port}")
    if args.host == "0.0.0.0" and (ip := lan_address()):
        print(f"  From your phone:  http://{ip}:{args.port}")
    print("  Stop with Ctrl+C\n", flush=True)

    uvicorn.run("server.app:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
