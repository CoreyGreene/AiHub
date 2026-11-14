"""SDXL models (Illustrious, Pony, plain SDXL ...) through diffusers / PyTorch.

Runs on cuda, mps or cpu. The model stays loaded between pictures; it is
only reloaded when a theme asks for a different one. LoRAs are swapped
in and out as themes need them.
"""

import gc

import torch
from diffusers import (
    AutoencoderKL,
    DPMSolverMultistepScheduler,
    EulerAncestralDiscreteScheduler,
    EulerDiscreteScheduler,
    StableDiffusionXLPipeline,
)

SCHEDULERS = {
    "euler_a": EulerAncestralDiscreteScheduler,
    "euler": EulerDiscreteScheduler,
    "dpm++": DPMSolverMultistepScheduler,
}


class Backend:
    def __init__(self, device: str):
        self.device = device
        # Half precision on graphics cards (CUDA and Apple), full on the CPU.
        self.dtype = torch.float32 if device == "cpu" else torch.float16
        self.pipe = None
        self.model = None
        self.loras = ()

    def is_loaded(self, req) -> bool:
        return self.model == (req["model"], req["low_memory"])

    def _load(self, req):
        key = (req["model"], req["low_memory"])
        if self.model == key:
            return
        self.pipe = self.model = None
        gc.collect()
        if self.device == "cuda":
            torch.cuda.empty_cache()
        extra = {}
        if req["low_memory"]:
            # 3060 settings, part 1: a VAE (the step that turns the result into
            # pixels) that works in half precision, so it isn't run at double
            # size. The stock SDXL VAE can't, and runs out of memory on 12 GB.
            extra["vae"] = AutoencoderKL.from_pretrained(
                req["fp16_vae"], torch_dtype=self.dtype, local_files_only=True
            )
        pipe = StableDiffusionXLPipeline.from_single_file(
            str(req["model"]), config=str(req["model_config"]), torch_dtype=self.dtype,
            local_files_only=True, **extra,
        )
        pipe.to(self.device)
        if req["low_memory"]:
            # Part 2: turn the result into pixels in tiles. Same picture, less memory.
            pipe.vae.enable_tiling()
        pipe.set_progress_bar_config(disable=True)
        self.pipe, self.model, self.loras = pipe, key, ()

    def _use_loras(self, loras):
        wanted = tuple((str(lora["path"]), float(lora["weight"])) for lora in loras)
        if wanted == self.loras:
            return
        self.pipe.unload_lora_weights()
        names = []
        for i, (path, _) in enumerate(wanted):
            name = f"lora{i}"
            self.pipe.load_lora_weights(path, adapter_name=name)
            names.append(name)
        if names:
            self.pipe.set_adapters(names, [weight for _, weight in wanted])
        self.loras = wanted

    def make(self, req: dict, on_step):
        self._load(req)
        self._use_loras(req["loras"])

        scheduler = SCHEDULERS[req.get("scheduler", "euler_a")]
        self.pipe.scheduler = scheduler.from_config(self.pipe.scheduler.config)

        steps = int(req["steps"])

        def step_end(pipe, step, timestep, kwargs):
            on_step(step + 1, steps)
            return kwargs

        generator = torch.Generator("cpu").manual_seed(int(req["seed"]))
        result = self.pipe(
            prompt=req["prompt"],
            negative_prompt=req["negative"],
            width=int(req["width"]),
            height=int(req["height"]),
            num_inference_steps=steps,
            guidance_scale=float(req["guidance"]),
            generator=generator,
            callback_on_step_end=step_end,
        )
        return result.images[0]
