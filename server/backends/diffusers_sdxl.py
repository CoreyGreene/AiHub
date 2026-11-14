"""SDXL models (Illustrious, Pony, plain SDXL ...) through diffusers / PyTorch.

Runs on cuda, mps or cpu. The model stays loaded between pictures; it is
only reloaded when a theme asks for a different one, or after it was let go
to free the graphics card's memory. LoRAs are swapped
in and out as themes need them.
"""

import gc

import torch
from compel import Compel, ReturnedEmbeddingsType
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
        self.compel = None  # reads long prompts in pieces (3060 settings only)
        self.model = None
        self.loras = ()

    def is_loaded(self, req) -> bool:
        return self.model == (req["model"], req["low_memory"])

    def unload(self):
        """Let go of the model and give its memory back to the graphics card."""
        self.pipe = self.compel = self.model = None
        self.loras = ()
        gc.collect()
        if self.device == "cuda":
            torch.cuda.empty_cache()
        elif self.device == "mps":
            torch.mps.empty_cache()

    def _load(self, req):
        key = (req["model"], req["low_memory"])
        if self.model == key:
            return
        self.unload()
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
        # 3060 settings, part 3: the model normally reads only the first 77
        # tokens of a prompt and drops the rest. Compel reads it in 75-token
        # pieces instead.
        self.compel = None if not req["low_memory"] else Compel(
            tokenizer=[pipe.tokenizer, pipe.tokenizer_2],
            text_encoder=[pipe.text_encoder, pipe.text_encoder_2],
            returned_embeddings_type=ReturnedEmbeddingsType.PENULTIMATE_HIDDEN_STATES_NON_NORMALIZED,
            requires_pooled=[False, True],
            truncate_long_prompts=False,
            device=self.device,
        )
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

    @torch.no_grad()
    def _encode(self, prompt: str, negative: str) -> dict:
        """Prompt and negative as model input, any length. Long ones come back
        as several pieces; the shorter one is padded with empty pieces so both
        are the same length (the model needs that)."""
        pos, pooled = self.compel(prompt)
        neg, neg_pooled = self.compel(negative)
        empty = self.compel("")[0]
        while pos.shape[1] < neg.shape[1]:
            pos = torch.cat([pos, empty], dim=1)
        while neg.shape[1] < pos.shape[1]:
            neg = torch.cat([neg, empty], dim=1)
        return dict(
            prompt_embeds=pos, pooled_prompt_embeds=pooled,
            negative_prompt_embeds=neg, negative_pooled_prompt_embeds=neg_pooled,
        )

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
            **(self._encode(req["prompt"], req["negative"]) if self.compel
               else dict(prompt=req["prompt"], negative_prompt=req["negative"])),
            width=int(req["width"]),
            height=int(req["height"]),
            num_inference_steps=steps,
            guidance_scale=float(req["guidance"]),
            generator=generator,
            callback_on_step_end=step_end,
        )
        return result.images[0]
