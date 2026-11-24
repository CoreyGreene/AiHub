"""Editing a picture with Qwen-Image-Edit-2511: a picture plus an
instruction ("make his cloak red") gives a new picture.

The drawing model is a 20B model: the full one from its folder (the Mac),
or a GGUF file ("gguf" in settings: 3-bit on the
12 GB card). With low_memory (generation.py measures the machine) the
text reader (Qwen2.5-VL 7B) is loaded in 4-bit, and the two take turns on
the card: the instruction is read first, then the reader is let go and the
drawing model loaded. Otherwise both stay loaded, the reader in full
precision (the Mac). A "Lightning" LoRA cuts the work to 8 steps with no
guidance.

    request: folder (the model folder), gguf, lightning (file names in it),
             image (PIL), prompt, width, height, steps, guidance, seed,
             low_memory
"""

import ctypes
import gc

import torch


class Backend:
    def __init__(self, device: str):
        self.device = device
        self.dtype = torch.bfloat16
        self.pipe = None
        self.folder = None
        self.reader = None  # the text reader, when on the card
        self.drawer = None  # the drawing model, when on the card

    def is_loaded(self, req: dict) -> bool:
        return self.pipe is not None and self.folder == req["folder"] and self.drawer is not None

    def unload(self):
        self.pipe = self.reader = self.drawer = None
        self.folder = None
        self._free()

    def _free(self):
        """Let go of freed memory, also back to the system: glibc otherwise
        keeps it, and the next big load (the drawing model passes through
        RAM) runs out on a 16 GB PC. (Only on Linux; elsewhere a no-op.)"""
        gc.collect()
        if self.device == "cuda":
            torch.cuda.empty_cache()
        elif self.device == "mps":
            torch.mps.empty_cache()
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except (OSError, AttributeError):
            pass

    # -- loading: the pipeline's small parts stay; reader and drawer take turns
    def _pipe(self, req):
        if self.pipe is not None and self.folder == req["folder"]:
            return
        from diffusers import AutoencoderKLQwenImage, QwenImageEditPlusPipeline

        self.unload()
        folder = str(req["folder"])
        vae = AutoencoderKLQwenImage.from_pretrained(folder, subfolder="vae", torch_dtype=self.dtype)
        self.pipe = QwenImageEditPlusPipeline.from_pretrained(
            folder, transformer=None, text_encoder=None, vae=vae, torch_dtype=self.dtype
        )
        self.pipe.vae.to(self.device)
        self.pipe.vae.enable_tiling()
        self.pipe.set_progress_bar_config(disable=True)
        self.folder = req["folder"]

    def _load_reader(self, req):
        if self.reader is not None:
            return
        self._drop_drawer(req)
        from transformers import Qwen2_5_VLForConditionalGeneration

        extra = {}
        if req["low_memory"]:
            from transformers import BitsAndBytesConfig

            extra["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=self.dtype
            )
        self.reader = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            str(req["folder"]), subfolder="text_encoder", torch_dtype=self.dtype, device_map=self.device, **extra
        )
        self.pipe.text_encoder = self.reader

    def _drop_reader(self, req):
        if self.reader is None or not req["low_memory"]:
            return
        self.pipe.text_encoder = self.reader = None
        self._free()

    def _load_drawer(self, req):
        if self.drawer is not None:
            return
        self._drop_reader(req)
        from diffusers import GGUFQuantizationConfig, QwenImageTransformer2DModel

        folder = req["folder"]
        if req.get("gguf"):  # a squeezed copy (the 12 GB card)
            self.drawer = QwenImageTransformer2DModel.from_single_file(
                str(folder / req["gguf"]),
                quantization_config=GGUFQuantizationConfig(compute_dtype=self.dtype),
                config=str(folder),
                subfolder="transformer",
                torch_dtype=self.dtype,
            )
        else:  # the full model, as it came (the Mac has room)
            self.drawer = QwenImageTransformer2DModel.from_pretrained(
                str(folder), subfolder="transformer", torch_dtype=self.dtype
            )
        self.drawer.to(self.device)
        self.pipe.transformer = self.drawer
        if req.get("lightning"):
            self.pipe.load_lora_weights(str(folder / req["lightning"]), adapter_name="lightning")

    def _drop_drawer(self, req):
        if self.drawer is None or not req["low_memory"]:
            return
        self.pipe.transformer = self.drawer = None
        self._free()

    # -- one edit
    def make(self, req: dict, on_step):
        from diffusers.pipelines.qwenimage.pipeline_qwenimage_edit_plus import CONDITION_IMAGE_SIZE, calculate_dimensions

        self._pipe(req)
        image = req["image"].convert("RGB")
        w, h = calculate_dimensions(CONDITION_IMAGE_SIZE, image.width / image.height)
        small = self.pipe.image_processor.resize(image, h, w)

        # 1. Read the instruction (with the picture), then let the reader go.
        self._load_reader(req)
        with torch.no_grad():
            embeds, mask = self.pipe.encode_prompt(image=[small], prompt=req["prompt"], device=self.device)
            negative = {}
            if req["guidance"] > 1:  # without Lightning: guidance needs a "not this" reading too
                ne, nm = self.pipe.encode_prompt(image=[small], prompt=" ", device=self.device)
                negative = dict(negative_prompt_embeds=ne, negative_prompt_embeds_mask=nm)

        # 2. Draw.
        self._load_drawer(req)
        steps = req["steps"]

        def step_done(pipe, i, t, kwargs):
            on_step(i + 1, steps)
            return kwargs

        with torch.no_grad():
            latents = self.pipe(
                image=[image],
                prompt_embeds=embeds,
                prompt_embeds_mask=mask,
                **negative,
                true_cfg_scale=req["guidance"],
                num_inference_steps=steps,
                width=req["width"],
                height=req["height"],
                generator=torch.Generator(self.device).manual_seed(req["seed"]),
                output_type="latent",
                callback_on_step_end=step_done,
            ).images
        return self._decode(latents, req)

    def _decode(self, latents, req):
        """Latents -> picture. If the card is too full next to the drawing
        model, let the drawing model go and try again."""
        vae = self.pipe.vae

        def run():
            with torch.no_grad():
                x = self.pipe._unpack_latents(latents, req["height"], req["width"], self.pipe.vae_scale_factor)
                x = x.to(vae.dtype)
                mean = torch.tensor(vae.config.latents_mean).view(1, vae.config.z_dim, 1, 1, 1)
                std = torch.tensor(vae.config.latents_std).view(1, vae.config.z_dim, 1, 1, 1)
                x = x * std.to(x.device, x.dtype) + mean.to(x.device, x.dtype)
                pixels = vae.decode(x, return_dict=False)[0][:, :, 0]
                return self.pipe.image_processor.postprocess(pixels, output_type="pil")[0]

        try:
            return run()
        except torch.OutOfMemoryError:
            latents = latents.cpu()
            self._drop_drawer({"low_memory": True})
            latents = latents.to(self.device)
            return run()
