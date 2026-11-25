# Bulk files

A bulk file is everything Code AI needs for one bulk job: the prompt, the items, and how to check each one. Code AI
knows nothing about any one kind of job, so a new kind of bulk job is a new file like these, never a code change.

On the Bulk tab, choose a file (or paste it), pick the folder it works in, and press Start. Claude can send the same
file with `codeai_bulk_start` (the JSON, or a path to the file, and the folder).

| File | What it does |
| --- | --- |
| `dialogue-replace.json` | Swaps lines of game dialogue for exact new words, with checks that the right line changed and its speaker, indent and #tags stayed |
| `dialogue-rework.json` | The new words are a rough idea: Gemma makes the line read right in the character's voice, then a review checks it |
| `summaries.json` | Reads files and says what's in each one, changing nothing (the smallest kind of file) |

## What a file can say

Only `prompt` and `items` are needed.

| Key | What it is |
| --- | --- |
| `prompt` | The instructions for **one** item. `{field}` is replaced by that item's field (`{old}`, `{file}`...), `{folder}` by the run's folder. A field an item doesn't have becomes "(not given)". One string, or a list of lines (easier to write). |
| `items` | The list of items, each an object with all its fields: `[{"character": "Becky", "old": "...", "new": "..."}, ...]`. One item per line is easiest to read. When you load the file, the page warns if items are missing a `{field}` the prompt uses. |
| `name` | Shown in the runs list, so you can find the run later. Left out, the file's name is used (`becky-fixes.json` is "becky-fixes"). |
| `model`, `thinking` | Which model (`gemma-31b`, `qwen-122b`...), and its thinking (`off`, `short`, `medium`, `on`...). The page can change them. |
| `can_change_files` | On unless the file says `false` (for a job that only reads). Every file is backed up first, so any item, or the whole run, can be undone. |
| `required` | Fields every item must have, e.g. `["old", "new"]`: a file with an item missing one won't start. Rarely needed: the page's warning covers most slips. |
| `search` | Text Code AI finds in the folder before the model starts, e.g. `"{old}"`. The matching lines go in the prompt, so it starts in the right place. |
| `checks` | Code AI's own tests of what each item changed (below). They run only when something changed. |
| `review` | A second prompt, asked fresh after a change passes its checks: it sees the change and answers PASS or FAIL. `{changes}` is the diff (added at the end if you leave it out), `{answer}` what the model said, plus the item's `{field}`s. |
| `retries` | How many more tries after a failed check or review (1). |
| `max_steps` | The most tool uses per item (12), so one it can't find doesn't search for minutes. |

## Checks

A list, run in order; the first that fails undoes the item and it's tried again with the reason. Text can use
`{field}`s; a check whose text needs a field the item doesn't have is skipped. Text is compared loosely: case, curly
quotes, `\` escapes and spacing don't matter.

| Check | Passes when |
| --- | --- |
| `{"type": "changed"}` | It changed at least one file. |
| `{"type": "lines", "most": 3, "in_place": true}` | At most `most` lines changed; `in_place`: each changed where it is, none added or taken out. |
| `{"type": "had", "text": "{old}"}` | A line it changed held this text before (it changed the right one). |
| `{"type": "has", "text": "{new}"}` | A line it changed has this text now. |
| `{"type": "kept", "pattern": "^\\s*[^:#]+:", "about": "the speaker's name"}` | In each changed line, what the regex matches is the same before and after. `about` names it in the reason. |
| `{"type": "lacks", "pattern": "regex", "about": "..."}` | No changed line matches the regex now: something that must never be there (in the dialogue files, a `#` meant as text that isn't written `\#`). |

`had` and `has` take `"share": 0.6` to ask for only that share of the text's words (words over 3 letters; `crash`
matches `crashed`), for when the wording can change.

If an item changes nothing although the file has checks, it's marked "not changed" (not retried): that's how a
line it can't find, or finds in two places, is left for you.
