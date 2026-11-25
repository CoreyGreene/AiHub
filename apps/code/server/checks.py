"""Checks and commands, in a sandbox: what the model may run to test its own work.

run_check: commands the user set for a project, picked by name. run_command (Can run commands): a command the model
chooses itself. Both run in the same sandbox (_profile).

The user writes them, the model only picks one by name: settings.local.json "checks", per folder,

    "checks": {"~/code/my-game": [{"name": "build", "command": "cmake --build build", "about": "builds the game"}]}

Each runs in the work folder, in a macOS sandbox (sandbox-exec) that the operating system enforces:
  - it can write only inside the work folder (and the system's temporary and cache folders), never in its .git;
  - it can't reach the internet;
  - it can't run git, under any path.
A check whose command mentions git is never run. It has a time limit, and the model gets its output back.
"""

import os
import re
import signal
import subprocess
import tempfile
from pathlib import Path

from . import settings

GIT_WORD = re.compile(r"(^|[^A-Za-z0-9_.-])git([^A-Za-z0-9_]|$)")
MAX_OUTPUT = 8000          # characters of output the model sees (the end, where the errors usually are)
DEFAULT_TIMEOUT = 300      # seconds


class CheckError(Exception):
    pass


def _key(folder) -> str:
    return str(Path(folder).expanduser().resolve())


def for_folder(folder: str) -> list[dict]:
    """The checks set for this folder: [{name, command, about, timeout}] (none with git in them)."""
    if not folder:
        return []
    want = _key(folder)
    for path, checks in (settings.get().get("checks") or {}).items():
        if _key(path) == want:
            return [c for c in checks if c.get("name") and c.get("command") and not GIT_WORD.search(c["command"])]
    return []


# Where deleting (and moving away) is allowed inside the work folder: what a build or a run makes again by itself.
REMAKEABLE = ("build", "build-[^/]*", "__pycache__", "\\.pytest_cache", "\\.cache", "node_modules", "dist", "out")


def _profile(work: Path) -> str:
    """The sandbox (macOS sandbox-exec, enforced by the system): everything as usual, except
      - writing anywhere but the work folder (and the system's temporary and cache folders);
      - deleting or moving away files in the work folder, but for build and cache folders (REMAKEABLE);
      - its .git: no reading, no writing; and git itself, under any path, never runs;
      - the internet."""
    quote = lambda p: '"' + str(p).replace("\\", "\\\\").replace('"', '\\"') + '"'
    home = Path.home().resolve()
    temp = ["/private/tmp", "/private/var/folders", home / "Library/Caches"]
    keep = "\n".join(f"    (require-not (subpath {quote(p)}))" for p in [work, *temp])
    keep_temp = "\n".join(f"    (require-not (subpath {quote(p)}))" for p in temp)
    root = re.escape(str(work)).replace('"', '\\"')
    remakeable = "|".join(REMAKEABLE)
    return f"""(version 1)
(allow default)
(deny network*)
(allow network* (local unix))
(deny file-write*
  (require-all
{keep}
    (require-not (literal "/dev/null"))
    (require-not (literal "/dev/tty"))
    (require-not (literal "/dev/dtracehelper"))))
(deny file-write-unlink
  (require-all
{keep_temp}
    (require-not (regex #"^{root}/(.*/)?({remakeable})(/|$)"))))
(deny file-read* file-write* (subpath {quote(work / ".git")}))
(deny process-exec (regex #"/git(-[a-z-]+)?$"))
"""


def run(work: str, name: str) -> tuple[str, str]:
    """Run the check called name in the work folder. Returns (output for the model, a short summary)."""
    found = next((c for c in for_folder(work) if c["name"].lower() == (name or "").strip().lower()), None)
    if found is None:
        names = ", ".join(c["name"] for c in for_folder(work)) or "none"
        raise CheckError(f"There's no check called {name!r} here. The checks: {names}.")
    passed, output = _sandboxed(Path(work).resolve(), found["command"], int(found.get("timeout") or DEFAULT_TIMEOUT))
    head = f"Check {found['name']} ({found['command']}): {'passed' if passed else 'FAILED'}."
    return f"{head}\n{output}", f"{found['name']}: {'passed' if passed else 'failed'}"


def run_command(work: str, command: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    """A command the model chose (Can run commands), in the work folder, in the same sandbox as the checks.
    Returns (output for the model, a short summary)."""
    command = (command or "").strip()
    if not command:
        raise CheckError("Give the command to run.")
    if GIT_WORD.search(command):
        raise CheckError("Git isn't allowed: the user does everything with Git themselves.")
    passed, output = _sandboxed(Path(work).resolve(), command, timeout)
    short = command if len(command) <= 60 else command[:57] + "..."
    return (f"$ {command}\n{'(it worked)' if passed else '(it failed)'}\n{output}",
            f"{short}: {'worked' if passed else 'failed'}")


def _sandboxed(folder: Path, command: str, timeout: int) -> tuple[bool, str]:
    """Run command with zsh in folder, inside the sandbox (_profile). (worked, output: its end if it's long)."""
    with tempfile.NamedTemporaryFile("w", suffix=".sb", delete=False) as f:
        f.write(_profile(folder))
        profile = f.name
    try:
        proc = subprocess.Popen(
            ["/usr/bin/sandbox-exec", "-f", profile, "/bin/zsh", "-c", command],
            cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
            env={**os.environ, "TERM": "dumb", "GIT_CONFIG_NOSYSTEM": "1"}, start_new_session=True,
        )
        try:
            output, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)  # it and everything it started
            proc.communicate()
            raise CheckError(f"That took longer than {timeout} seconds and was stopped.")
    finally:
        os.unlink(profile)
    output = (output or "").strip()
    if len(output) > MAX_OUTPUT:
        output = "... (the start cut)\n" + output[-MAX_OUTPUT:]
    return proc.returncode == 0, (output or "(no output)") + ("" if proc.returncode == 0 else f"\n(exit {proc.returncode})")
