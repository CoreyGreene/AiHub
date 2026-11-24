"""Wan video models (Wan 2.1, and Wan 2.2 text-to-video) through diffusers /
PyTorch. The model is a folder in diffusers format (model_index.json inside).

Runs on cuda, mps or cpu. The model stays loaded between videos; it is only
reloaded when a theme asks for a different one, or after it was let go to
free the graphics memory. LoRAs are swapped in and out as themes need them.

With low_memory (the "Use 3060 settings" switch) the text reader (a 6B
umT5, stored in full precision: 23 GB) is loaded in 4-bit (still 5.5 GB:
its word list is huge), frames are turned into pixels in tiles, and the
video model waits in normal memory while that happens. Wan 2.1 1.3B then
fits a 12 GB card, and a 16 GB PC.
On the Mac everything loads in bfloat16.
"""

import ctypes
import gc

import torch
from diffusers import AutoencoderKLWan, FlowMatchEulerDiscreteScheduler, UniPCMultistepScheduler, WanPipeline

# Samplers. "default" is the one the model came with (UniPC with Wan's
# flow shift); the others start from its settings.
SCHEDULERS = {
    "unipc": UniPCMultistepScheduler,
    "flow_euler": FlowMatchEulerDiscreteScheduler,
}


class Backend:
    def __init__(self, device: str):
        self.device = device
        self.dtype = torch.float32 if device == "cpu" else torch.bfloat16
        self.pipe = None
        self.model = None
        self.loras = ()
        self.scheduler_config = None  # the model's own sampler settings

    def is_loaded(self, req) -> bool:
        return self.model == (req["model"], req["low_memory"])

    def unload(self):
        """Let go of the model and give its memory back."""
        self.pipe = self.model = self.scheduler_config = None
        self.loras = ()
        gc.collect()
        if self.device == "cuda":
            torch.cuda.empty_cache()
        elif self.device == "mps":
            torch.mps.empty_cache()
        self._trim()

    def _trim(self):
        """Hand freed normal memory back to the system (glibc keeps it
        otherwise; matters on a 16 GB PC). Only on Linux; elsewhere a no-op."""
        gc.collect()
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except (OSError, AttributeError):
            pass

    def _load(self, req):
        key = (req["model"], req["low_memory"])
        if self.model == key:
            return
        self.unload()
        folder = str(req["model"])
        extra = {}
        if req["low_memory"]:
            from transformers import BitsAndBytesConfig, UMT5EncoderModel

            extra["text_encoder"] = UMT5EncoderModel.from_pretrained(
                folder, subfolder="text_encoder", torch_dtype=self.dtype, device_map=self.device,
                quantization_config=BitsAndBytesConfig(
                    load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=self.dtype
                ),
            )
        # Wan's VAE is made to run in full precision (it's small).
        vae = AutoencoderKLWan.from_pretrained(folder, subfolder="vae", torch_dtype=torch.float32)
        pipe = WanPipeline.from_pretrained(folder, vae=vae, torch_dtype=self.dtype, **extra)
        if req["low_memory"]:
            # The 4-bit reader is already on the card; move the rest.
            pipe.transformer.to(self.device)
            pipe.vae.to(self.device)
            pipe.vae.enable_tiling()
        else:
            pipe.to(self.device)
        pipe.set_progress_bar_config(disable=True)
        self.pipe, self.model, self.loras = pipe, key, ()
        self._trim()
        self.scheduler_config = pipe.scheduler.config

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

    def _use_scheduler(self, name: str):
        config = self.scheduler_config
        if name in SCHEDULERS:
            shift = {"shift": config.get("flow_shift", 3.0)} if name == "flow_euler" else {}
            self.pipe.scheduler = SCHEDULERS[name].from_config(config, **shift)
        else:  # "default": the model's own, as it came
            from diffusers import schedulers

            self.pipe.scheduler = getattr(schedulers, config["_class_name"]).from_config(config)

    def make(self, req: dict, on_step) -> list:
        self._load(req)
        self._use_loras(req["loras"])
        self._use_scheduler(req.get("scheduler", "default"))

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
            # Wan makes 4n+1 frames; round down to the nearest that fits.
            num_frames=max(1, (int(req["frames"]) - 1) // 4 * 4 + 1),
            num_inference_steps=steps,
            guidance_scale=float(req["guidance"]),
            generator=generator,
            output_type="latent",
            callback_on_step_end=step_end,
        )
        return self._decode(result.frames, req)

    @torch.no_grad()
    def _decode(self, latents, req) -> list:
        """Latents -> frames. With low_memory the video model waits in normal
        memory meanwhile (2.7 GB), so the card has room to make the pixels."""
        if req["low_memory"]:
            self.pipe.transformer.to("cpu")
            torch.cuda.empty_cache()
        try:
            vae = self.pipe.vae
            x = latents.to(vae.dtype)
            mean = torch.tensor(vae.config.latents_mean).view(1, vae.config.z_dim, 1, 1, 1)
            std = torch.tensor(vae.config.latents_std).view(1, vae.config.z_dim, 1, 1, 1)
            x = x * std.to(x.device, x.dtype) + mean.to(x.device, x.dtype)
            pixels = vae.decode(x, return_dict=False)[0]
            return self.pipe.video_processor.postprocess_video(pixels, output_type="pil")[0]
        finally:
            if req["low_memory"]:
                self.pipe.transformer.to(self.device)
                self._trim()
