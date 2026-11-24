"""What the model can look at: read-only tools over the folders settings.local.json allows ("folders").

    list_files(path)                     a folder's files and folders
    find_files(name, path)               files whose name matches (* and ? wildcards), anywhere under a folder
    read_file(path, start_line, end_line)
    search(pattern, path)                lines matching a regular expression, in text files under a folder

With "Can change files" on (off by default), two more, each change backed up first so the answer can be undone:
    write_file(path, content)            make a file, or replace one whole
    replace_in_file(path, old_text, new_text)
Nothing is ever deleted. A path must be inside an allowed folder (symlinks followed first, so a link can't lead out).
"""

import difflib
import fnmatch
import hashlib
import json
import shutil
import threading
import uuid
from contextlib import contextmanager
import os
import re
from pathlib import Path

from . import settings

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".cache", "build", "DerivedData", ".Trash"}
MAX_LIST, MAX_FOUND, MAX_MATCHES = 300, 200, 100
MAX_LINES, MAX_BYTES, SEARCH_FILE_BYTES = 800, 200_000, 2_000_000


class ToolError(Exception):
    pass


_scope = threading.local()


@contextmanager
def scoped(paths: list[str] | None):
    """While a bulk job works, its tools see only its own folder (inside the allowed ones), on this thread only."""
    _scope.folders = [{"name": Path(p).name, "path": str(Path(p).expanduser().resolve())} for p in paths] if paths else None
    try:
        yield
    finally:
        _scope.folders = None


def inside_allowed(raw: str) -> Path | None:
    """raw as a folder inside one of the allowed folders, or None."""
    path = Path(raw or "").expanduser().resolve()
    roots = [Path(f["path"]) for f in folders()]
    return path if path.is_dir() and any(path == r or r in path.parents for r in roots) else None


def folders() -> list[dict]:
    """The allowed folders: [{name, path}], only those that exist (a bulk job's own folder while it works)."""
    if getattr(_scope, "folders", None):
        return _scope.folders
    out = []
    for f in settings.get().get("folders", []):
        path = Path(f["path"]).expanduser().resolve()
        if path.is_dir():
            out.append({"name": f.get("name", path.name), "path": str(path)})
    return out


def browse(raw: str = "", ext: str = "") -> dict:
    """For the page's folder picker: the folders (and, with ext like ".json", those files) in a folder inside the
    allowed ones. No folder: the allowed folders themselves. up: the folder above, or "" at the top."""
    if not raw:
        return {"path": "", "name": "Your folders", "up": None,
                "folders": [{"name": f["name"], "path": f["path"]} for f in folders()], "files": []}
    path = inside_allowed(raw)
    if path is None:
        raise ToolError("That folder isn't inside your allowed ones.")
    roots = [Path(f["path"]) for f in folders()]
    up = "" if path in roots else str(path.parent)
    subs, files = [], []
    try:
        entries = sorted(path.iterdir(), key=lambda e: e.name.lower())
    except OSError as err:
        raise ToolError(f"Can't open {path}: {err.strerror}.")
    for e in entries:
        if e.name.startswith(".") or e.name in SKIP_DIRS:
            continue
        if e.is_dir():
            subs.append({"name": e.name, "path": str(e)})
        elif ext and e.suffix.lower() == ext.lower() and e.is_file():
            files.append({"name": e.name, "path": str(e)})
    return {"path": str(path), "name": path.name, "up": up, "folders": subs, "files": files}


def _resolve(raw: str, new_ok: bool = False) -> Path:
    roots = [Path(f["path"]) for f in folders()]
    if not roots:
        raise ToolError("No folders are allowed (settings.local.json: folders).")
    raw = (raw or "").strip()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        # a bare name like "Desktop" or "Desktop/notes.txt": one of the allowed folders by name
        first, _, rest = raw.partition("/")
        named = next((Path(f["path"]) for f in folders() if f["name"].lower() == first.lower()), None)
        path = (named / rest) if named else roots[0] / raw
    path = path.resolve()
    if not any(path == r or r in path.parents for r in roots):
        allowed = ", ".join(f["path"] for f in folders())
        raise ToolError(f"{path} is outside the folders you may look at ({allowed}).")
    if not path.exists():
        if new_ok and path.parent.is_dir():
            return path
        raise ToolError(f"{path} doesn't exist." + (" Its folder doesn't either." if new_ok else ""))
    return path


def _size(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024


def list_files(path: str = "") -> tuple[str, str]:
    folder = _resolve(path)
    if not folder.is_dir():
        raise ToolError(f"{folder} is a file, not a folder: use read_file.")
    entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    entries = [p for p in entries if p.name != ".DS_Store"]
    lines = []
    for p in entries[:MAX_LIST]:
        try:
            lines.append(f"{p.name}/" if p.is_dir() else f"{p.name}  ({_size(p.stat().st_size)})")
        except OSError:
            lines.append(p.name)
    more = f"\n... and {len(entries) - MAX_LIST} more" if len(entries) > MAX_LIST else ""
    text = f"{folder}:\n" + ("\n".join(lines) or "(empty)") + more
    return text, f"{len(entries)} items"


def _walk(folder: Path):
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            yield Path(root) / name


def find_files(name: str, path: str = "") -> tuple[str, str]:
    folder = _resolve(path)
    pattern = name if any(c in name for c in "*?[") else f"*{name}*"
    found = []
    for p in _walk(folder):
        if fnmatch.fnmatch(p.name.lower(), pattern.lower()):
            found.append(str(p))
            if len(found) >= MAX_FOUND:
                break
    more = f"\n(stopped at {MAX_FOUND})" if len(found) >= MAX_FOUND else ""
    return ("\n".join(found) or f"No files named like '{name}' under {folder}.") + more, f"{len(found)} found"


def _is_text(path: Path) -> bool:
    with open(path, "rb") as f:
        return b"\0" not in f.read(4096)


def read_file(path: str, start_line: int = 1, end_line: int = 0) -> tuple[str, str]:
    file = _resolve(path)
    if file.is_dir():
        raise ToolError(f"{file} is a folder: use list_files.")
    if not _is_text(file):
        raise ToolError(f"{file} isn't a text file ({_size(file.stat().st_size)}).")
    lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(int(start_line or 1), 1)
    end = min(int(end_line or 0) or start + MAX_LINES - 1, start + MAX_LINES - 1, len(lines))
    body = "\n".join(f"{n:>5}  {lines[n - 1]}" for n in range(start, end + 1))[:MAX_BYTES]
    note = f"\n(lines {start}-{end} of {len(lines)}; ask for more with start_line)" if end < len(lines) or start > 1 else ""
    return f"{file}:\n{body}{note}", f"{end - start + 1 if lines else 0} lines"


def search(pattern: str, path: str = "") -> tuple[str, str]:
    folder = _resolve(path)
    try:
        regex = re.compile(pattern, re.I)
    except re.error as err:
        raise ToolError(f"That pattern isn't a valid regular expression: {err}")
    files = [folder] if folder.is_file() else _walk(folder)
    matches = []
    for p in files:
        try:
            if p.stat().st_size > SEARCH_FILE_BYTES or not _is_text(p):
                continue
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{p}:{n}: {line.strip()[:200]}")
                    if len(matches) >= MAX_MATCHES:
                        break
        except OSError:
            continue
        if len(matches) >= MAX_MATCHES:
            break
    more = f"\n(stopped at {MAX_MATCHES})" if len(matches) >= MAX_MATCHES else ""
    return ("\n".join(matches) or f"No lines match '{pattern}' under {folder}.") + more, f"{len(matches)} matches"


# ---------- changing files (only with "Can change files" on) ----------

NO_WRITE = {".git", ".venv", "node_modules", "__pycache__"}
MAX_WRITE = 1_000_000
RUNNABLE = {".command", ".sh", ".zsh", ".bash"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Changes:
    """The files one answer changed, each backed up first (in backups/<id>/), so the answer can be undone."""

    def __init__(self):
        self.id = uuid.uuid4().hex
        self.files: list[dict] = []   # {path, existed, backup, after, diff}

    def _entry(self, path: Path) -> dict:
        """This file's record, made (and the file backed up) the first time this answer changes it."""
        for f in self.files:
            if f["path"] == str(path):
                return f
        folder = settings.folder("backups_dir") / self.id
        folder.mkdir(parents=True, exist_ok=True)
        entry = {"path": str(path), "existed": path.exists(), "backup": "", "before": ""}
        if path.exists():
            backup = folder / f"{len(self.files)}-{path.name}"
            shutil.copy2(path, backup)
            entry["backup"] = str(backup)
            entry["before"] = path.read_text(encoding="utf-8", errors="replace")
        self.files.append(entry)
        return entry

    def write(self, path: Path, text: str, runnable: bool = False) -> str:
        entry = self._entry(path)
        path.write_text(text, encoding="utf-8")
        # asked for, or a script (a #! first line, or .command / .sh / .zsh): marked runnable
        made = self._runnable(path, entry) if runnable or text.startswith("#!") or path.suffix in RUNNABLE else False
        entry["after"] = _sha(path.read_bytes())
        diff = difflib.unified_diff(entry["before"].splitlines(), text.splitlines(),
                                    "before" if entry["existed"] else "(new file)", path.name, lineterm="", n=2)
        entry["diff"] = "\n".join(list(diff)[2:])[:20000]
        added = sum(1 for l in entry["diff"].splitlines() if l.startswith("+"))
        removed = sum(1 for l in entry["diff"].splitlines() if l.startswith("-"))
        return f"+{added} -{removed} lines" + (", made runnable" if made else "")

    def make_runnable(self, path: Path) -> bool:
        """Mark a file runnable (chmod +x). False if it already was."""
        entry = self._entry(path)
        made = self._runnable(path, entry)
        entry["after"] = _sha(path.read_bytes())
        entry.setdefault("diff", "")
        return made

    def _runnable(self, path: Path, entry: dict) -> bool:
        mode = path.stat().st_mode
        if mode & 0o111 == 0o111:
            return False
        path.chmod(mode | 0o111)
        entry["runnable"] = True
        return True

    def summary(self) -> list[dict]:
        """What the page and History keep: path, new or changed, made runnable, the diff, and what Undo needs."""
        keys = ("path", "existed", "backup", "after", "diff", "runnable")
        return [{k: f[k] for k in keys if k in f} for f in self.files]


def _check_writable(path: Path) -> None:
    if any(part in NO_WRITE for part in path.parts):
        raise ToolError(f"{path} is inside a folder that's never changed ({', '.join(sorted(NO_WRITE))}).")
    if path.is_dir():
        raise ToolError(f"{path} is a folder.")
    if path.exists() and not _is_text(path):
        raise ToolError(f"{path} isn't a text file: it won't be changed.")


def write_file(path: str, content: str, changes: Changes, runnable: bool = False) -> tuple[str, str]:
    file = _resolve(path, new_ok=True)
    _check_writable(file)
    if len(content.encode()) > MAX_WRITE:
        raise ToolError("That's too big to write in one go (1 MB at most).")
    what = changes.write(file, content, runnable in (True, "true", "True", 1))
    return f"Wrote {file} ({what}).", f"wrote it ({what})"


def make_runnable(path: str, changes: Changes) -> tuple[str, str]:
    file = _resolve(path)
    _check_writable(file)
    if changes.make_runnable(file):
        return f"{file} is runnable now.", "made it runnable"
    return f"{file} was already runnable.", "already runnable"


def replace_in_file(path: str, old_text: str, new_text: str, changes: Changes) -> tuple[str, str]:
    file = _resolve(path)
    _check_writable(file)
    text = file.read_text(encoding="utf-8")
    count = text.count(old_text) if old_text else 0
    if count == 0 and old_text.strip() and "\n" not in old_text.strip():
        # one line, right but for the spaces at its start or end (models often get an indent wrong): if exactly one
        # line of the file matches it that way, change that line, keeping the file's own indent
        lines = text.split("\n")
        hits = [n for n, line in enumerate(lines) if line.strip() == old_text.strip()]
        if len(hits) == 1 and "\n" not in new_text.strip():
            line = lines[hits[0]]
            lines[hits[0]] = line[: len(line) - len(line.lstrip())] + new_text.strip()
            what = changes.write(file, "\n".join(lines))
            return (f"Changed {file} line {hits[0] + 1} ({what}). Your old_text's indent was off, so the line kept "
                    "the file's own indent.", f"changed line {hits[0] + 1} ({what}; indent kept)")
    if count == 0:
        close = difflib.get_close_matches(old_text.strip(), [l.strip() for l in text.splitlines()], n=1, cutoff=0.6)
        hint = ""
        if close:
            n = next(i for i, l in enumerate(text.splitlines(), 1) if l.strip() == close[0])
            hint = f" The closest line is line {n}, exactly: {text.splitlines()[n - 1]!r}"
        raise ToolError(f"old_text isn't in {file} exactly as given (spaces and line breaks count).{hint} "
                        "Copy it exactly from the file.")
    if count > 1:
        raise ToolError(f"old_text is in {file} {count} times: include more lines around it so it's only once.")
    what = changes.write(file, text.replace(old_text, new_text, 1))
    return f"Changed {file} ({what}).", f"changed it ({what})"


def undo(files: list[dict]) -> list[str]:
    """Put an answer's files back as they were. A file changed again since is left alone (and said so)."""
    notes = []
    for f in reversed(files):
        path = Path(f["path"])
        now = path.read_bytes() if path.exists() else None
        if now is not None and f.get("after") and _sha(now) != f["after"]:
            notes.append(f"{path} was changed again since, so it was left as it is.")
            continue
        if f["existed"]:
            shutil.copy2(f["backup"], path)
            notes.append(f"{path} is back as it was.")
        elif now is not None:
            path.unlink()
            notes.append(f"{path} was new, so it was removed.")
    return notes


def _tool(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required}}}


_PATH = {"type": "string", "description": "A full path (~ is fine) inside an allowed folder"}

DEFINITIONS = [
    _tool("list_files", "List the files and folders in a folder.", {"path": _PATH}, ["path"]),
    _tool("find_files", "Find files by name anywhere under a folder. * and ? work as wildcards.",
          {"name": {"type": "string"}, "path": _PATH}, ["name", "path"]),
    _tool("read_file", "Read a text file, with line numbers (800 lines at a time).",
          {"path": _PATH, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, ["path"]),
    _tool("search", "Search text files under a folder (or one file) for lines matching a regular expression "
          "(case doesn't matter).", {"pattern": {"type": "string"}, "path": _PATH}, ["pattern", "path"]),
]
EDIT_DEFINITIONS = [
    _tool("write_file", "Make a new text file, or replace a whole file's text. Read a file before replacing it. "
          "runnable: true marks it runnable (executable), for a script the user will run or double-click.",
          {"path": _PATH, "content": {"type": "string", "description": "The whole new text of the file"},
           "runnable": {"type": "boolean", "description": "Mark the file runnable (executable)"}},
          ["path", "content"]),
    _tool("make_runnable", "Mark a file as runnable (executable, like chmod +x): a script or a .command file the "
          "user can double-click. write_file can do it too, with runnable: true.", {"path": _PATH}, ["path"]),
    _tool("replace_in_file", "Change part of a text file: old_text (copied exactly from the file, found once) "
          "becomes new_text. Best for small changes.",
          {"path": _PATH, "old_text": {"type": "string"}, "new_text": {"type": "string"}},
          ["path", "old_text", "new_text"]),
]
_RUN = {"list_files": list_files, "find_files": find_files, "read_file": read_file, "search": search}
_EDIT = {"write_file": write_file, "replace_in_file": replace_in_file, "make_runnable": make_runnable}
_KNOWN = {"path", "name", "pattern", "start_line", "end_line", "content", "old_text", "new_text", "runnable"}
_ALIASES = {"folder": "path", "dir": "path", "directory": "path", "file": "path", "file_path": "path",
            "filename": "path", "query": "pattern", "regex": "pattern", "text": "content",
            "old": "old_text", "new": "new_text", "old_string": "old_text", "new_string": "new_text",
            "executable": "runnable"}


def run(name: str, arguments: str, changes: Changes | None = None) -> tuple[str, str, bool]:
    """Run a tool the model asked for: (result for the model, a short summary for the page, ok). changes: this
    answer's Changes when it may change files, else None."""
    try:
        args = json.loads(arguments or "{}") if isinstance(arguments, str) else dict(arguments or {})
        allowed = {**_RUN, **(_EDIT if changes else {})}
        if name in _EDIT and not changes:
            raise ToolError("Changing files is switched off for this question: say what you would change instead.")
        if name not in allowed:
            raise ToolError(f"There's no tool called {name}. The tools: {', '.join(allowed)}.")
        # small models sometimes name an argument differently ("folder" for "path"): read it the way it was meant
        args = {_ALIASES.get(k, k): v for k, v in args.items()}
        args = {k: v for k, v in args.items() if k in _KNOWN}
        if name in _EDIT:
            args["changes"] = changes
        text, summary = allowed[name](**args)
        return text, summary, True
    except ToolError as err:
        return f"Error: {err}", str(err), False
    except (TypeError, ValueError) as err:
        return f"Error: those arguments don't fit {name} ({err}).", "wrong arguments", False
    except OSError as err:
        return f"Error: {err.strerror or err}", err.strerror or str(err), False


def instructions(can_edit: bool = False) -> str:
    """What the model is told about itself and the folders, at the start of every question."""
    allowed = "\n".join(f"- {f['name']}: {f['path']}" for f in folders()) or "- (none)"
    if can_edit:
        rights = (
            "For this question you may also change files, with write_file, replace_in_file and make_runnable, "
            "inside the same folders. Read a file before changing it, change only what the question needs, and "
            "prefer replace_in_file for small changes. Nothing can be deleted. When you're done, say which files "
            "you changed and what you changed in each.\n"
            "Runnable files: you can mark a file runnable (executable) yourself: write_file with runnable: true, or "
            "make_runnable for a file that's already there. Scripts with a #! first line, and .command, .sh and "
            ".zsh files, are marked runnable anyway. On this Mac, double-clicking a .py file opens it in an editor, "
            "so when the user wants something to run with a double-click, also write a .command file (#!/bin/bash, "
            "then the command, e.g. cd to the script's folder and run python3 on it) and mark it runnable; that's "
            "the file they double-click. Don't send them to Automator or the Terminal to do it. python3 on this Mac is "
            "Python 3.12 (Homebrew, with tkinter for windows and pop-ups): use python3, never /usr/bin/python3 "
            "(macOS's old 3.9)."
        )
    else:
        rights = ("You can't change, move or delete anything: if the question needs a change, show it (the code "
                  "or the new text) and say where it goes.")
    return (
        "You are a helpful coding assistant running locally on the user's Mac. You can look at files on this Mac "
        "with your tools (list_files, find_files, read_file, search), but only inside these folders:\n"
        f"{allowed}\n"
        f"{rights} When a question is about the user's files or projects, look first instead of guessing or "
        "telling them to do it themselves; say which files you looked at. When you write code, put it in a fenced "
        "code block with its language."
    )
