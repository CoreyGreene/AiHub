# Themes: how to set one up

A **theme** is one JSON file in this folder (`server/theme/`). It says which
AI video model to use, which LoRAs to add, the words to put around the
user's prompt, and the video settings (size, length, steps). The website
reads this folder every time, so adding or editing a theme needs **no code
change and no restart**. Themes can also be made and changed on the
website, on the Theme tab:

- **Edit**: pick a theme, press Change (name, prompt words, model, LoRAs,
  size, frames, frames a second, steps, guidance, sampler). Other keys in
  the file, like `_notes`, are kept as they are.
- **New**: the same form, empty. Making it writes a new file here, named
  after the theme (`My Hero` → `my-hero.json`).
- Both can **add a model or LoRA file**, on a computer (not shown on
  phones): drop a `.safetensors` file on the box under Model or LoRAs, or
  press Choose a file. It's put in the right folder and picked. Only
  `.safetensors` (`.ckpt` files can carry code that runs when loaded).

**Not set up yet:** no video backend is written, so Generate answers "Not
connected yet". Themes can still be made, changed and looked at.

**Theme files stay on your machine.** They hold your own choices of model,
LoRAs and prompt words, so `server/theme/*.json` is git-ignored. What's
shared is this guide and the generic examples in `server/theme/examples/`.

This file is for anyone setting up a theme, people and AI agents alike.

## Where the files go

```
server/
  aIModels/                 AI models (NOT in git)
    my-wan-model/           a video model in diffusers format (a folder
                            with model_index.json inside), or
    my-video-model.safetensors   a single-file model
    safety/                 the two nudity checkers (needed, always on)
  lora/                     LoRAs (NOT in git)
    my-motion-lora.safetensors
  theme/
    my-theme.json           your themes (NOT in git)
    README.md               this file (in git)
    examples/               generic starting points (in git)
      wan-example.json
```

- **Models** go in `server/aIModels/`. Video models usually come as a
  folder (several parts: the video model, a text encoder, a VAE); put the
  whole folder there. It shows up in the Model list if it has a
  `model_index.json` inside.
- **LoRAs** go in `server/lora/`.
- **Themes** go in `server/theme/`, one `.json` file each.

A theme names its model and LoRAs by **name only**. The site adds the
folder itself, so a theme never contains a path like `/home/...` or
`C:\...`.

These folders can be moved (for example to a bigger drive on the Mac) by
setting `models_dir` or `loras_dir` in `server/settings.local.json`. Theme
files don't change when you do that.

## Adding a new theme, step by step

1. **Put the model** in `server/aIModels/`.
2. **Put any LoRAs** (`.safetensors`) in `server/lora/`.
3. **Copy** `examples/wan-example.json` up into `server/theme/` under a
   new name, e.g. `hero-idle.json`. The file name (without `.json`) becomes
   the theme's id; use lowercase and dashes. (Files inside `examples/` are
   never shown on the site.)
4. **Edit** the copy: `name`, `hint`, `model`, `loras`, `prompt`,
   `negative` and the settings (see the table below).
5. **Reload the page.** The theme shows up in the Create drop list. Open
   the **Theme** tab to see exactly what it does; a red **file not found**
   tag means the model or LoRA name doesn't match what's in the folder.

If a theme file is broken (bad JSON, or a required key is missing), the site
skips it and prints why in the server's terminal.

## Every key in a theme file

| Key | Needed? | What it is | Example |
| --- | --- | --- | --- |
| `name` | yes | Shown in the drop list | `"My Theme"` |
| `hint` | no | Short line under the name | `"Idle loops, plain background"` |
| `backend` | yes | How the model is run (see below) | `"diffusers-wan"` |
| `model` | yes | Model folder or file name in `server/aIModels/` | `"my-wan-model"` |
| `model_config` | no | A config folder in `server/aIModels/`, for single-file models that need one | `"wan-config"` |
| `loras` | no | List of LoRA files in `server/lora/`, each with a strength (`weight`, usually 0.5 to 1.0) | `[{"file": "my-motion-lora.safetensors", "weight": 0.8}]` |
| `prompt` | yes | Words around the user's prompt. **Must contain `{prompt}`**: that's where the user's words go | `"game character, {prompt}, smooth motion"` |
| `negative` | no | Things the model should avoid | `"blurry, jittery, flickering"` |
| `width`, `height` | no (832, 480) | Video size in pixels, in steps of 16. 832×480 is Wan's "480p"; 1280×720 is 720p | `832`, `480` |
| `frames` | no (81) | How many pictures the video has. Wan likes 4n+1 (49, 81, 121) | `81` |
| `fps` | no (16) | Frames a second. 81 frames at 16 fps is about 5 seconds | `16` |
| `steps` | no (30) | More = more detail, slower | `30` |
| `guidance` | no (5.0) | How closely it follows the prompt | `5.0` |
| `scheduler` | no (`default`) | Sampler: `default` (the model's own, usually best), `unipc` or `flow_euler` | `"default"` |
| `_notes` | no | A note for people; shown on the Theme tab, not used for the video | `"Why this theme exists"` |

Any key starting with `_` is a note and is ignored when making videos.

### Backends

| `backend` | Runs | State |
| --- | --- | --- |
| `diffusers-wan` | Wan 2.1 / 2.2 video models with PyTorch on CUDA, Apple (MPS) or CPU | planned (phase 3, on the Mac) |

More backends (MLX for the Mac, other video models) will be added in
`server/backends/`; a theme picks one by name.

## What always gets added (you don't put this in the theme)

- **Safety words** from `server/settings.json` (`safety.negative`) are added
  to every theme's `negative`.
- **The nudity check** runs on every video, in every theme: frames from all
  through the video are checked. If it flags one, the video is made again
  (up to 2 tries) and is never shown. There is no way to turn it off from a
  theme.

## Rules (this repo is public)

- **Safe for work only.** No NSFW themes, no NSFW LoRAs, no adult words in
  `prompt`.
- **Never commit model, LoRA or theme files.** `server/aIModels/`,
  `server/lora/` and `server/theme/*.json` are git-ignored. Only generic
  examples (with made-up names) go in `server/theme/examples/`.
- **Nothing private** in a theme: no personal paths, names, keys or
  addresses.
- **Check the licence** of a model or LoRA before using it for game art
  (selling videos, credit needed?) and note it in `_notes`.

## Example

See [`examples/wan-example.json`](examples/wan-example.json): a complete
theme with made-up names. Copy it, then change it. To see what any of your
own themes does, open the **Theme** tab on the website.
