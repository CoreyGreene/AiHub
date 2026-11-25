"""Where videos are kept on disk (the outputs folder, never in git).

    outputs/new/<id>.mp4                 just made, not saved yet
    outputs/characters/<folder>/<id>.mp4 saved to a character
    outputs/start-pictures/<id>.png      pictures a video can begin from
    ...each with <id>.jpg beside it (the first frame, shown before it plays)
    and <id>.json: theme, prompt, seed, frames, fps, character, time.
"""

import io
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import settings

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _new() -> Path:
    return settings.folder("outputs_dir") / "new"


def _characters() -> Path:
    return settings.folder("outputs_dir") / "characters"


def keep_start_picture(data: bytes) -> str:
    """Keep a picture sent to begin videos from (any common format, made a
    PNG). Returns its id. Raises ValueError if it isn't a picture."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as opened:
            # Phone photos say which way up they are in a tag: turn them that way.
            picture = ImageOps.exif_transpose(opened).convert("RGB")
    except (UnidentifiedImageError, OSError) as err:
        raise ValueError("That file isn't a picture.") from err
    return _keep_start(picture)


def _keep_start(picture) -> str:
    folder = settings.folder("outputs_dir") / "start-pictures"
    folder.mkdir(parents=True, exist_ok=True)
    pic_id = uuid.uuid4().hex
    picture.save(folder / f"{pic_id}.png")
    return pic_id


def rotate_start_picture(pic_id: str) -> str | None:
    """A quarter turn clockwise, kept as a new start picture (so the page
    never shows an old copy). Returns its id, or None if it isn't here."""
    from PIL import Image

    path = start_picture(pic_id)
    if path is None:
        return None
    with Image.open(path) as opened:
        turned = opened.convert("RGB").transpose(Image.Transpose.ROTATE_270)
    return _keep_start(turned)


def start_picture(pic_id: str) -> Path | None:
    if not ID_PATTERN.match(pic_id):
        return None
    path = settings.folder("outputs_dir") / "start-pictures" / f"{pic_id}.png"
    return path if path.is_file() else None


def urls(vid_id: str) -> dict:
    """Where the page gets a video and its first frame."""
    return {"file": f"api/videos/{vid_id}", "poster": f"api/videos/{vid_id}/poster"}


def keep_new(frames: list, fps: int, info: dict) -> str:
    """Save a freshly made video (its frames, as PIL images) into outputs/new
    as an .mp4, with its first frame as a .jpg, and return its id. If the
    backend made the .mp4 itself (info["_file"], with sound), that file is
    kept as it is."""
    import imageio.v3 as iio  # comes with the video packages
    import numpy as np

    folder = _new()
    folder.mkdir(parents=True, exist_ok=True)
    vid_id = uuid.uuid4().hex
    made = info.pop("_file", None)
    if made:
        shutil.move(str(made), folder / f"{vid_id}.mp4")
    else:
        # H.264 in yuv420p plays on every phone; quality 8 of 10 keeps detail.
        iio.imwrite(
            folder / f"{vid_id}.mp4",
            np.stack([np.asarray(f.convert("RGB")) for f in frames]),
            fps=fps, codec="libx264", quality=8, pixelformat="yuv420p",
        )
    frames[0].convert("RGB").save(folder / f"{vid_id}.jpg", quality=90)
    info = {"id": vid_id, **info, "made": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (folder / f"{vid_id}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return vid_id


def read_frames(path: Path) -> list:
    """A video file's frames, as PIL images (for the safety check)."""
    import imageio.v3 as iio
    from PIL import Image

    return [Image.fromarray(frame) for frame in iio.imiter(path)]


def find(vid_id: str, suffix: str = ".mp4") -> Path | None:
    """The video file (or with suffix=".jpg", its first frame) for an id,
    wherever it is kept."""
    if not ID_PATTERN.match(vid_id):
        return None
    for path in [_new() / f"{vid_id}{suffix}", *_characters().glob(f"*/{vid_id}{suffix}")]:
        if path.is_file():
            return path
    return None


def info(vid_id: str) -> dict | None:
    """The settings saved beside a video."""
    video = find(vid_id)
    if video is None:
        return None
    try:
        return json.loads(video.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def is_saved(path: Path) -> bool:
    return path.parent.parent == _characters()


def folder_name(character: str) -> str:
    """A safe folder name for a character: 'Grim the Goblin' -> 'grim-the-goblin'."""
    return re.sub(r"[^a-z0-9]+", "-", character.lower()).strip("-")


def save_to_character(vid_id: str, character: str) -> None:
    """Move a video (and its first frame and settings) into the character's folder."""
    video = find(vid_id)
    if video is None:
        raise FileNotFoundError(vid_id)
    folder = _characters() / folder_name(character)
    folder.mkdir(parents=True, exist_ok=True)

    info_path = video.with_suffix(".json")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    info["character"] = character
    (folder / f"{vid_id}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    if info_path.parent != folder:
        info_path.unlink()
    for path in (video, video.with_suffix(".jpg")):
        if path.parent != folder and path.is_file():
            shutil.move(path, folder / path.name)


def delete_saved(vid_ids: list[str]) -> int:
    """Delete saved videos (with their first frame and settings) for good.
    A character left with no videos goes too. Returns how many were deleted."""
    done = 0
    for vid_id in vid_ids:
        video = find(vid_id)
        if video is None or not is_saved(video):
            continue
        for path in (video, video.with_suffix(".jpg"), video.with_suffix(".json")):
            path.unlink(missing_ok=True)
        done += 1
        folder = video.parent
        if not any(folder.glob("*.mp4")):
            for leftover in [*folder.glob("*.json"), *folder.glob("*.jpg")]:
                leftover.unlink()
            try:
                folder.rmdir()
            except OSError:  # something else is in it (e.g. .DS_Store): leave it
                pass
    return done


def _read_folder(folder: Path) -> list[dict]:
    """The settings of every video in a character's folder, oldest first."""
    infos = []
    for path in folder.glob("*.json"):
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (folder / f"{info.get('id')}.mp4").is_file():
            infos.append(info)
    infos.sort(key=lambda i: i.get("made", ""))
    return infos


def list_characters() -> list[dict]:
    """Every character, with its first video's first frame as the cover."""
    out = []
    root = _characters()
    if not root.is_dir():
        return out
    for folder in root.iterdir():
        infos = _read_folder(folder) if folder.is_dir() else []
        if not infos:
            continue
        out.append({
            "name": infos[0].get("character", folder.name),
            "folder": folder.name,
            "count": len(infos),
            "cover": urls(infos[0]["id"])["poster"],
        })
    out.sort(key=lambda c: c["name"].lower())
    return out


def character(folder_id: str) -> dict | None:
    """One character and all of its videos, oldest first."""
    if folder_id != folder_name(folder_id) or not folder_id:
        return None
    folder = _characters() / folder_id
    infos = _read_folder(folder) if folder.is_dir() else []
    if not infos:
        return None
    return {
        "name": infos[0].get("character", folder_id),
        "folder": folder_id,
        "videos": [
            {
                "id": i["id"],
                **urls(i["id"]),
                "theme": i.get("theme", ""),
                "prompt": i.get("prompt", ""),
                "seconds": round(i["frames"] / i["fps"], 1) if i.get("frames") and i.get("fps") else None,
                "made": i.get("made", ""),
            }
            for i in infos
        ],
    }
