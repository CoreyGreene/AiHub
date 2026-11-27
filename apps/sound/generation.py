"""Load Stable Audio 3 Small SFX from AiHub's local SoundModels folder."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL = "stable-audio-3-small-sfx"
MODEL_NAME = "Stable Audio 3 Small SFX"
STEPS = 8
_model = None
_FUSED_MAPPINGS = (
    "pretransform.model.encoder.layers.0.mapping",
    "pretransform.model.decoder.layers.3.mapping",
)
_CONVOLUTIONS = (
    "model.model.preprocess_conv.weight",
    "model.model.postprocess_conv.weight",
)


def model_folder() -> Path:
    return Path(os.environ.get("AIHUB_MODELS_DIR", ROOT / "models")).expanduser() / MODEL


def model_ready() -> bool:
    folder = model_folder()
    return all((folder / name).is_file() for name in (
        "model_config.json", "model.safetensors", "t5gemma-b-b-ul2/config.json",
        "t5gemma-b-b-ul2/model.safetensors", "t5gemma-b-b-ul2/tokenizer.json",
    ))


def _load_weights(model, checkpoint: Path) -> None:
    from safetensors.torch import load_file
    from stable_audio_3.loading_utils import remap_state_dict_keys

    expected = model.state_dict()
    weights = remap_state_dict_keys(load_file(str(checkpoint)), expected)
    # Some Small SFX checkpoints export these as [out, kernel, in].
    # The PyTorch decoder also expects its fused mapping kernels split into weight norm.
    for key in _CONVOLUTIONS:
        if key in weights and weights[key].shape != expected[key].shape:
            weights[key] = weights[key].transpose(1, 2).contiguous()
    for prefix in _FUSED_MAPPINGS:
        key = f"{prefix}.weight"
        vector = f"{prefix}.weight_v"
        scale = f"{prefix}.weight_g"
        if key not in weights or vector not in expected:
            continue
        kernel = weights.pop(key)
        if kernel.shape != expected[vector].shape:
            kernel = kernel.transpose(1, 2).contiguous()
        magnitude = kernel.float().norm(dim=(1, 2), keepdim=True).to(kernel.dtype)
        weights[vector] = kernel
        weights[scale] = magnitude
    # A disabled bottleneck can have an empty buffer absent from the checkpoint.
    for key, tensor in expected.items():
        if tensor.numel() == 0:
            weights.setdefault(key, tensor)
    model.load_state_dict(weights)


def load():
    global _model
    if _model is not None:
        return _model
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    import torch
    from stable_audio_3 import StableAudioModel
    from stable_audio_3.factory import create_diffusion_cond_from_config

    folder = model_folder()
    from aihub_room import make_room

    make_room("sound", folder)
    config = json.loads((folder / "model_config.json").read_text())
    for entry in config["model"]["conditioning"]["configs"]:
        if entry["type"] == "t5gemma":
            encoder = entry["config"]
            encoder["model_path"] = str(folder / encoder.pop("subfolder"))
    device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    half = device == "cuda"
    model = create_diffusion_cond_from_config(config)
    _load_weights(model, folder / "model.safetensors")
    model.to(device).eval().requires_grad_(False)
    if half:
        model.to(torch.float16)
    model.use_lora = False
    model.lora_names = []
    _model = StableAudioModel(model, config, device, half)
    return _model


def make(prompt: str, seconds: float, seed: int, path: Path, progress) -> None:
    import numpy as np
    import soundfile

    model = load()
    progress("Generating", 0)
    samples = model.generate(prompt=prompt, duration=seconds, seed=seed, steps=STEPS,
                             callback=lambda step: progress("Generating", step["i"] + 1),
                             disable_tqdm=True)
    progress("Writing audio", STEPS)
    audio = samples[0].float().cpu().numpy().T
    if not audio.size or not np.isfinite(audio).all():
        raise ValueError("The model did not return usable audio.")
    peak = float(np.abs(audio).max())
    if peak > 0:
        audio *= .95 / peak
    soundfile.write(path, audio, model.model.sample_rate, format="WAV", subtype="PCM_16")
