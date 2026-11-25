"""LTX-2.5 through MLX (Apple's framework), with the ltx-2-mlx port. Mac only.

It makes the video and its sound together. With a start picture ("image"
in the request) the video begins from that picture (picture to video), and
takes its shape: a square picture makes a square video, a tall one a tall
video, with about as many pixels as the theme's width x height.

The model is a folder in the port's layout (config.json,
transformer-distilled.safetensors, the Gemma-4 text reader in its own
folder, the upscaler, the video and sound decoders). It runs the distilled
pipeline: the video is made at half size (8 steps), scaled up 2x and
finished (3 more steps). So "steps" and "guidance" don't apply.

frames: how many, 8k + 1 (rounded down to fit); 0 = the model picks the
length from the prompt (1 to 20 seconds). Width and height are rounded down
to steps of 64.

Unlike the other backends, make() returns the finished .mp4 (frames and
sound), not a list of frames: generation.py reads its frames to check them.
"""

import gc
import os
import tempfile
from pathlib import Path

# Never download anything: every part must be in the model folder. (Without
# this, a pack it doesn't fully recognise makes it fetch a text reader from
# Hugging Face by itself, gigabytes, and the wrong one.)
os.environ["HF_HUB_OFFLINE"] = "1"


class Backend:
    def __init__(self, device: str):
        if device != "mps":
            from . import NotReady

            raise NotReady("LTX-2.5 (MLX) runs on a Mac only.")
        self.pipe = None
        self.model = None
        self.folder = Path(tempfile.mkdtemp(prefix="movieai-ltx-"))

    def is_loaded(self, req) -> bool:
        return self.pipe is not None and self.model == req["model"]

    def unload(self):
        self.pipe = self.model = None
        gc.collect()
        try:
            import mlx.core as mx

            mx.clear_cache()
        except (ImportError, AttributeError):
            pass

    def _load(self, req):
        if self.is_loaded(req):
            return
        self.unload()
        from ltx_pipelines_mlx import DistilledPipeline

        # low_memory: let go of each part once it's done (the text reader,
        # then the video model before the decoders). Keeps the peak down;
        # each video loads them again from disk, which is quick next to the work.
        self.pipe = DistilledPipeline(model_dir=str(req["model"]), low_memory=True)
        self.model = req["model"]

    def _shape(self, image: Path, width: int, height: int) -> tuple[Path, int, int]:
        """The video takes the start picture's shape (square, tall or wide),
        with about as many pixels as the theme's size: nothing is cut off
        and there are no bars. The picture is scaled to that size (a sliver
        may be trimmed to reach steps of 64). Returns (picture, width, height)."""
        from PIL import Image, ImageOps

        with Image.open(image) as opened:
            picture = opened.convert("RGB")
        area, ratio = width * height, picture.width / picture.height
        w = max(64, round((area * ratio) ** 0.5 / 64) * 64)
        h = max(64, round((area / ratio) ** 0.5 / 64) * 64)
        out = self.folder / f"start-{image.stem}-{w}x{h}.png"
        ImageOps.fit(picture, (w, h), Image.LANCZOS).save(out)
        return out, w, h

    def make(self, req: dict, on_step) -> Path:
        from ltx_pipelines_mlx.utils.types import DEFAULT_AUTO_DURATION

        self._load(req)
        on_step(0, 0)
        frames = int(req["frames"])
        width = max(64, int(req["width"]) // 64 * 64)
        height = max(64, int(req["height"]) // 64 * 64)
        image = None
        if req.get("image"):
            image, width, height = self._shape(Path(req["image"]), width, height)
        out = self.folder / f"{req['seed']}.mp4"
        self.pipe.generate_and_save(
            prompt=req["prompt"],
            output_path=str(out),
            width=width,
            height=height,
            num_frames=(frames - 1) // 8 * 8 + 1 if frames > 0 else DEFAULT_AUTO_DURATION,
            frame_rate=float(req["fps"]),
            seed=int(req["seed"]),
            image=str(image) if image else None,
        )
        if image:
            image.unlink(missing_ok=True)
        return out
