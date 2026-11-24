"""Runs inside TRELLIS's own Python (trellis-mac/.venv), started by server/trellis.py.

    <trellis-mac>/.venv/bin/python -u trellis_worker.py <trellis-mac folder>

Loads TRELLIS.2 once and keeps it loaded. Reads one job per line on stdin (JSON):
    {"id", "image", "out", "seed", "texture_size", "pipeline_type"}
and answers on stdout with lines that start with MARK (everything else on stdout
is TRELLIS talking, and is ignored):
    {"id", "stage": "loading" | "shape" | "texture" | "saving"}
    {"id", "done": true, "glb", "seconds", "vertices", "faces"}
    {"id", "error": "..."}
Only Apple Silicon with the Metal texture tools built (see trellis-mac/CLAUDE.md).
The export follows trellis-mac/generate.py (its Metal bake path).
"""

import json
import os
import sys
import time

MARK = "@@MESHAI "
TRELLIS = os.path.abspath(sys.argv[1])

# Same set-up as generate.py, before torch is imported anywhere.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("ATTN_BACKEND", "sdpa")
os.environ.setdefault("SPARSE_ATTN_BACKEND", "sdpa")
try:
    import flex_gemm  # noqa: F401

    os.environ.setdefault("SPARSE_CONV_BACKEND", "flex_gemm")
except (ImportError, RuntimeError):
    os.environ.setdefault("SPARSE_CONV_BACKEND", "none")
sys.path.insert(0, os.path.join(TRELLIS, "TRELLIS.2"))
sys.path.append(os.path.join(TRELLIS, "stubs"))
os.chdir(TRELLIS)

import torch  # noqa: E402
from PIL import Image  # noqa: E402


def say(**message) -> None:
    sys.stdout.write(MARK + json.dumps(message) + "\n")
    sys.stdout.flush()


_pipeline = None


def pipeline():
    global _pipeline
    if _pipeline is None:
        from trellis2.pipelines.trellis2_image_to_3d import Trellis2ImageTo3DPipeline

        local = os.path.join(TRELLIS, "local-model")
        path = local if os.path.exists(os.path.join(local, "pipeline.json")) else "microsoft/TRELLIS.2-4B"
        _pipeline = Trellis2ImageTo3DPipeline.from_pretrained(path)
        _pipeline.to(torch.device("mps"))
    return _pipeline


def _metal_bake_ready():
    """o_voxel's Metal bake, with generate.py's grid_sample fix when flex_gemm is absent."""
    import o_voxel.postprocess as post

    if not (getattr(post, "_BACKEND", None) == "metal" and getattr(post, "_HAS_DR", False)):
        raise RuntimeError("The Metal texture tools aren't built (see trellis-mac/CLAUDE.md).")
    if not getattr(post, "_HAS_FLEX_GEMM", False):
        import torch.nn.functional as F

        def grid_sample_3d(feats, coords, shape, grid, mode="trilinear"):
            B, C, D, H, W = shape[0], shape[1], shape[2], shape[3], shape[4]
            dense = torch.zeros(B, C, D, H, W, dtype=feats.dtype, device=feats.device)
            dense[coords[:, 0].long(), :, coords[:, 1].long(), coords[:, 2].long(), coords[:, 3].long()] = feats
            g = torch.stack([grid[..., 2] / (W - 1) * 2 - 1, grid[..., 1] / (H - 1) * 2 - 1,
                             grid[..., 0] / (D - 1) * 2 - 1], dim=-1).reshape(B, 1, 1, -1, 3)
            out = F.grid_sample(dense, g, mode="bilinear", align_corners=True, padding_mode="border")
            return out.reshape(B, C, grid.shape[1]).permute(0, 2, 1).reshape(B * grid.shape[1], C)

        post._grid_sample_3d = grid_sample_3d
    return post


def make(job: dict) -> dict:
    jid = job["id"]
    if _pipeline is None:
        say(id=jid, stage="loading")
    pipe = pipeline()
    say(id=jid, stage="shape")
    t0 = time.time()
    image = Image.open(job["image"])
    out = pipe.run(image, seed=int(job["seed"]), pipeline_type=str(job.get("pipeline_type", "512")))
    mesh = out[0] if isinstance(out, list) else out
    verts, faces = mesh.vertices, mesh.faces
    if verts.shape[0] == 0 or faces.shape[0] == 0:
        raise RuntimeError("TRELLIS made an empty model. On a Mac this is usually the GPU watchdog: "
                           "try again with fewer windows open.")

    say(id=jid, stage="texture")
    post = _metal_bake_ready()
    import fast_simplification

    target = min(200000, int(faces.shape[0]))  # the Metal BVH is unstable above ~800k faces
    if faces.shape[0] > target:
        v, f = fast_simplification.simplify(verts.cpu().numpy(), faces.cpu().numpy(), 1.0 - target / faces.shape[0])
        verts = torch.from_numpy(v).float()
        faces = torch.from_numpy(f.astype("int32"))
    glb = post.to_glb(vertices=verts.cpu(), faces=faces.cpu(), attr_volume=mesh.attrs.cpu(),
                      coords=mesh.coords.cpu(), attr_layout=mesh.layout, voxel_size=mesh.voxel_size,
                      aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]], decimation_target=target,
                      texture_size=int(job.get("texture_size", 1024)), verbose=False)
    say(id=jid, stage="saving")
    os.makedirs(os.path.dirname(job["out"]), exist_ok=True)
    glb.export(job["out"])
    seconds = round(time.time() - t0, 1)
    return {"glb": job["out"], "seconds": seconds,
            "vertices": int(len(glb.vertices)) if hasattr(glb, "vertices") else None,
            "faces": int(len(glb.faces)) if hasattr(glb, "faces") else None}


def main() -> None:
    say(ready=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        job = json.loads(line)
        try:
            say(id=job["id"], done=True, **make(job))
        except Exception as err:  # report it and keep the model loaded for the next job
            import traceback

            traceback.print_exc(file=sys.stderr)
            say(id=job["id"], error=f"{type(err).__name__}: {err}")
        finally:
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()


if __name__ == "__main__":
    main()
