"""Workflows are JSON files in the workflows folder (server/workflow/ by
default; personal, so never committed). A workflow is a name and a list of
items; each item is what the Advanced or Custom tab would send to Generate
(prompt, how many, theme + its words, or a custom theme) plus a name for
where its pictures go in staging. The id is the file name without .json.
"""

import json
import re

from . import jobs, pictures, settings

# The last Start of each workflow (while the server runs): one entry per
# item, {"job": job id, "staging": group name}. Kept in memory only.
_runs: dict[str, list[dict]] = {}


def _folder():
    return settings.folder("workflows_dir")


def _read(path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        print(f"Skipping workflow {path.name}: {err}")
        return None


def listing() -> list[dict]:
    """Every workflow: id, name, how many items, newest change first."""
    found = []
    for path in _folder().glob("*.json"):
        flow = _read(path)
        if flow is not None:
            found.append((path.stat().st_mtime, {"id": path.stem, "name": flow.get("name", path.stem), "items": len(flow.get("items", []))}))
    return [flow for _, flow in sorted(found, key=lambda pair: pair[0], reverse=True)]


def get(flow_id: str) -> dict | None:
    if not re.fullmatch(r"[a-z0-9-]+", flow_id):
        return None
    path = _folder() / f"{flow_id}.json"
    flow = _read(path) if path.is_file() else None
    return None if flow is None else {"id": flow_id, "name": flow.get("name", flow_id), "items": flow.get("items", [])}


def create(name: str) -> str:
    """A new, empty workflow, named after itself ('Space Dinos' ->
    space-dinos.json, or space-dinos-2.json if that's taken). Returns its id."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workflow"
    folder = _folder()
    folder.mkdir(parents=True, exist_ok=True)
    flow_id, n = base, 1
    while (folder / f"{flow_id}.json").exists():
        n += 1
        flow_id = f"{base}-{n}"
    save(flow_id, {"name": name, "items": []})
    return flow_id


def save(flow_id: str, flow: dict) -> None:
    """Write the whole workflow (name and items). The id stays the same
    when it's renamed. A changed workflow's last run report no longer fits
    its boxes, so it's dropped."""
    _runs.pop(flow_id, None)
    path = _folder() / f"{flow_id}.json"
    # Write to a spare file first, so a crash can't leave half a workflow.
    spare = path.with_suffix(".json.saving")
    spare.write_text(json.dumps({"name": flow["name"], "items": flow["items"]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    spare.replace(path)


def delete(flow_id: str) -> bool:
    if get(flow_id) is None:
        return False
    (_folder() / f"{flow_id}.json").unlink()
    return True


def staging_name(flow: dict, index: int) -> str:
    """Where an item's pictures go: its name, or the workflow's + its number."""
    return flow["items"][index].get("name") or f"{flow['name']} {index + 1}"


def is_running(flow_id: str) -> bool:
    return any(jobs.is_active(entry["job"]) for entry in _runs.get(flow_id, []))


def start(flow_id: str, parts: list[tuple]) -> None:
    """Queue every item: parts is (theme id, theme, prompt, count) per item,
    already checked. Each item's staging group is fixed now."""
    flow = get(flow_id)
    run = []
    for n, (theme_id, theme, prompt, count) in enumerate(parts):
        name = staging_name(flow, n)
        run.append({"job": jobs.submit(theme_id, theme, prompt, count, staging=name), "staging": name})
    _runs[flow_id] = run


def run_status(flow_id: str) -> list[dict]:
    """The last Start's progress, one per item (the job's status, or
    "done" once the queue has forgotten it)."""
    out = []
    for entry in _runs.get(flow_id, []):
        job = jobs.status(entry["job"]) or {"status": "done", "pictures": [], "count": 0}
        folder = pictures.folder_name(entry["staging"]) or "unnamed"
        out.append({**job, "staging": entry["staging"], "folder": folder})
    return out
