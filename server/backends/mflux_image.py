"""Text-to-picture models through mflux (Apple's MLX): Qwen-Image and FLUX.2 klein. Mac only.

A model is a folder in models_dir (a Hugging Face download, or an MLX copy already made smaller such as
mlx-community's 8-bit one), plus its kind:

    "qwen-image"      Qwen-Image (2512): has a negative prompt, about 30-50 steps, guidance about 4
    "flux2-klein-4b"  FLUX.2 klein 4B: no negative prompt, 4 steps, guidance 1

request: folder (full path), kind, quantize (None, 4 or 8: makes a full model smaller as it loads),
prompt, negative, width, height, steps, guidance, seed. The model stays loaded between pictures and is
only loaded again for a different folder (or after unload()).
"""

import gc


class _Steps:
    """mflux calls this after every step: passes it on as on_step(done, total)."""

    def __init__(self):
        self.on_step = None

    def call_in_loop(self, t, seed, prompt, latents, config, time_steps):
        if self.on_step:
            self.on_step(t + 1, config.num_inference_steps)


class Backend:
    def __init__(self, device: str):
        self.model = None
        self.key = None
        self.steps = _Steps()

    def is_loaded(self, req) -> bool:
        return self.key == (str(req["folder"]), req["kind"], req.get("quantize"))

    def unload(self):
        import mlx.core as mx

        self.model = self.key = None
        gc.collect()
        mx.clear_cache()

    def _load(self, req):
        if self.is_loaded(req):
            return
        self.unload()
        from mflux.models.common.config import ModelConfig

        folder, kind, quantize = str(req["folder"]), req["kind"], req.get("quantize")
        if kind == "qwen-image":
            from mflux.models.qwen.variants.txt2img.qwen_image import QwenImage

            model = QwenImage(quantize=quantize, model_path=folder, model_config=ModelConfig.qwen_image())
        elif kind == "flux2-klein-4b":
            from mflux.models.flux2.variants import Flux2Klein

            model = Flux2Klein(quantize=quantize, model_path=folder, model_config=ModelConfig.flux2_klein_4b())
        else:
            raise ValueError(f"mflux doesn't know the kind '{kind}'. Known: qwen-image, flux2-klein-4b")
        model.callbacks.register(self.steps)
        self.model, self.key = model, (folder, kind, quantize)

    def make(self, req, on_step):
        self._load(req)
        self.steps.on_step = on_step
        try:
            args = dict(seed=req["seed"], prompt=req["prompt"], num_inference_steps=req["steps"],
                        width=req["width"], height=req["height"], guidance=req["guidance"])
            if req["kind"] == "qwen-image":
                out = self.model.generate_image(**args, negative_prompt=req.get("negative") or None)
                self.model.prompt_cache.clear()  # every prompt is kept otherwise
            else:  # FLUX.2 has no negative prompt
                out = self.model.generate_image(**args, scheduler="flow_match_euler_discrete")
        finally:
            self.steps.on_step = None
        return out.image.convert("RGB")
