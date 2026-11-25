"""After every edit, is the file still valid? A quick syntax check by its kind, so a broken edit is caught at once
(the model is told, with the line, and fixes it). Nothing is run: these only parse.

    .py                     Python compiles it (in this program)
    .json                   it parses
    .sh .zsh .bash .command shells' -n (read, don't run); a #! file names its shell
    .js .mjs .cjs           the Mac's own JavaScript engine (JavaScriptCore) parses it, as a module or a script
    .c .cpp .h ...          clang -fsyntax-only, only when the project's build/compile_commands.json says how

Other kinds aren't checked (None). Returns "" when it's fine, else what's wrong.
"""

import json
import shlex
import subprocess
from pathlib import Path

JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"
SHELLS = {".sh": "/bin/bash", ".bash": "/bin/bash", ".zsh": "/bin/zsh", ".command": "/bin/zsh"}
C_LIKE = {".c", ".cc", ".cpp", ".cxx", ".m", ".mm"}
TIMEOUT = 20


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return ""  # the checker itself didn't work: say nothing rather than something wrong
    return "" if done.returncode == 0 else (done.stderr or done.stdout).strip()[-2000:]


def _javascript(path: Path) -> str:
    if not Path(JSC).exists():
        return ""
    quoted = json.dumps(str(path))
    module = _run([JSC, "-e", f"checkModuleSyntax(read({quoted}))"])
    if not module or "Exception" not in module:
        return ""
    script = _run([JSC, "-e", f"checkSyntax({quoted})"])  # an older-style script that isn't a valid module
    return "" if not script or "Exception" not in script else module.replace("Exception: ", "")


def _c_like(path: Path) -> str | None:
    """With the project's compile_commands.json (CMake's CMAKE_EXPORT_COMPILE_COMMANDS), its own command for this
    file, with -fsyntax-only. Without one: not checked (guessing the include folders gives wrong errors)."""
    for parent in path.parents:
        for db in parent.glob("build*/compile_commands.json"):
            try:
                entries = json.loads(db.read_text())
            except (OSError, ValueError):
                continue
            for e in entries:
                if Path(e.get("directory", "."), e.get("file", "")).resolve() == path:
                    args = e.get("arguments") or shlex.split(e.get("command", ""))
                    keep, skip = [], False
                    for a in args:  # drop the output: -o FILE and -c
                        if skip:
                            skip = False
                            continue
                        if a == "-o":
                            skip = True
                            continue
                        if a != "-c":
                            keep.append(a)
                    return _run(keep + ["-fsyntax-only"], Path(e.get("directory", ".")))
        if (parent / ".git").exists():
            break
    return None


def check(path: Path) -> str | None:
    """"" = fine, text = what's wrong, None = this kind isn't checked."""
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if suffix == ".py":
        try:
            compile(text, str(path), "exec")
            return ""
        except SyntaxError as err:
            return f"line {err.lineno}: {err.msg}"
    if suffix == ".json":
        try:
            json.loads(text)
            return ""
        except ValueError as err:
            return str(err)
    shell = SHELLS.get(suffix)
    if not shell and text.startswith("#!"):
        first = text.split("\n", 1)[0]
        shell = "/bin/zsh" if "zsh" in first else "/bin/bash" if ("bash" in first or first.endswith("/sh")) else None
    if shell:
        return _run([shell, "-n", str(path)])
    if suffix in (".js", ".mjs", ".cjs"):
        return _javascript(path)
    if suffix in C_LIKE:
        return _c_like(path)
    return None
