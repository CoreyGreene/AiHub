# Themes: how to set one up

A **theme** is one JSON file in this folder (`server/theme/`). It says which
AI model to use, which LoRAs to add, the words to put around the user's
prompt, and the picture settings. The website reads this folder every time,
so adding or editing a theme needs **no code change and no restart**.
An existing theme can also be changed on the website: Theme tab → Change
(name, prompt words, model, LoRAs, size, steps, guidance, sampler). Other
keys in the file, like `_notes`, are kept as they are.

**Theme files stay on your machine.** They hold your own choices of model,
LoRAs and prompt words, so `server/theme/*.json` is git-ignored. What's
shared is this guide and the generic examples in `server/theme/examples/`.

This file is for anyone setting up a theme, people and AI agents alike.

## Where the files go

```
server/
  aIModels/                 AI models (NOT in git)
    my-sdxl-model.safetensors   a checkpoint
    sdxl-config/            SDXL config + tokenizer files, no weights (needed)
    sdxl-vae-fp16-fix/      used by the "Use 3060 settings" switch
    safety/                 the two nudity checkers (needed, always on)
  lora/                     LoRAs (NOT in git)
    my-style-lora.safetensors
  theme/
    my-theme.json           your themes (NOT in git)
    README.md               this file (in git)
    examples/               generic starting points (in git)
      sdxl-example.json
```

- **Models** go in `server/aIModels/`.
- **LoRAs** go in `server/lora/`.
- **Themes** go in `server/theme/`, one `.json` file each.

A theme names its model and LoRAs by **file name only**. The site adds the
folder itself, so a theme never contains a path like `/home/...` or
`C:\...`. A subfolder is fine (`"model": "sdxl/myModel.safetensors"`), as
long as it's inside `server/aIModels/` or `server/lora/`.

These folders can be moved (for example to a bigger drive on the Mac) by
setting `models_dir` or `loras_dir` in `server/settings.local.json`. Theme
files don't change when you do that.

## Adding a new theme, step by step

1. **Put the model** (`.safetensors`) in `server/aIModels/`.
2. **Put any LoRAs** (`.safetensors`) in `server/lora/`.
3. **Copy** `examples/sdxl-example.json` up into `server/theme/` under a
   new name, e.g. `pixel-hero.json`. The file name (without `.json`) becomes
   the theme's id; use lowercase and dashes. (Files inside `examples/` are
   never shown on the site.)
4. **Edit** the copy: `name`, `hint`, `model`, `loras`, `prompt`,
   `negative` and the settings (see the table below).
5. **Reload the page.** The theme shows up in the Create drop list. Open
   the **Theme** tab to see exactly what it does; a red **file not found**
   tag means the model or LoRA file name doesn't match a file in the folder.

If a theme file is broken (bad JSON, or a required key is missing), the site
skips it and prints why in the server's terminal.

## Every key in a theme file

| Key | Needed? | What it is | Example |
| --- | --- | --- | --- |
| `name` | yes | Shown in the drop list | `"My Theme"` |
| `hint` | no | Short line under the name | `"Flat colours, bold outlines"` |
| `backend` | yes | How the model is run (see below) | `"diffusers-sdxl"` |
| `model` | yes | Model file name in `server/aIModels/` | `"my-sdxl-model.safetensors"` |
| `model_config` | yes for SDXL | Config folder in `server/aIModels/` | `"sdxl-config"` |
| `loras` | no | List of LoRA files in `server/lora/`, each with a strength (`weight`, usually 0.5 to 1.0) | `[{"file": "my-style-lora.safetensors", "weight": 0.7}]` |
| `prompt` | yes | Words around the user's prompt. **Must contain `{prompt}`**: that's where the user's words go | `"best quality, {prompt}, full body, white background"` |
| `negative` | no | Things the model should avoid | `"lowres, blurry, text, watermark"` |
| `width`, `height` | no (1024) | Picture size in pixels. For SDXL keep the total near 1024×1024, in steps of 64 | `832`, `1216` |
| `steps` | no (28) | More = more detail, slower | `28` |
| `guidance` | no (6.0) | How closely it follows the prompt (5 to 8 is usual) | `6.0` |
| `scheduler` | no (`euler_a`) | Sampler: `euler_a`, `euler` or `dpm++` | `"euler_a"` |
| `_notes` | no | A note for people; shown on the Theme tab, not used for the picture | `"Why this theme exists"` |

Any key starting with `_` is a note and is ignored when making pictures.

### Backends

| `backend` | Runs | Needs |
| --- | --- | --- |
| `diffusers-sdxl` | SDXL-based checkpoints (SDXL, Illustrious, NoobAI, Pony…) with PyTorch on CUDA, Apple (MPS) or CPU | `model_config: "sdxl-config"` |

More backends (MLX, Core ML for the Mac) will be added in
`server/backends/`; a theme picks one by name.

## What always gets added (you don't put this in the theme)

- **Safety words** from `server/settings.json` (`safety.negative`) are added
  to every theme's `negative`.
- **The nudity check** runs on every picture, in every theme. If it flags a
  picture, the picture is made again (up to 3 tries) and is never shown.
  There is no way to turn it off from a theme.

## Rules (this repo is public)

- **Safe for work only.** No NSFW themes, no NSFW LoRAs, no adult words in
  `prompt`.
- **Never commit model, LoRA or theme files.** `server/aIModels/`,
  `server/lora/` and `server/theme/*.json` are git-ignored. Only generic
  examples (with made-up file names) go in `server/theme/examples/`.
- **Nothing private** in a theme: no personal paths, names, keys or
  addresses.
- **Check the licence** of a model or LoRA before using it for game art
  (selling pictures, credit needed?) and note it in `_notes`.

## Example

See [`examples/sdxl-example.json`](examples/sdxl-example.json): a complete
theme with made-up file names. Copy it, then change it. To see what any of
your own themes does, open the **Theme** tab on the website.
