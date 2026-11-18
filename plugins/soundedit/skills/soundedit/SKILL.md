---
name: soundedit
description: Edit audio and work through sample folders in SoundEdit, the Mac audio editor and sample manager, with SoundEdit's MCP tools while the person watches and listens. Use when the person asks you to edit, trim, fade, normalize, slice, stretch or mark a sound open in SoundEdit, or to sort, name, tag or make kits from a folder of samples.
---

SoundEdit is open on the person's Mac, and they watch and listen while you work. They decide what to keep, what to call it and where it goes; SoundEdit does the measuring and the editing. The `soundedit` MCP server's tools reach it.

- Read `get_state` first. Select a range (`set_selection`) before a range edit. Times are seconds unless an argument names another unit; for an exact selection use `start_frame` and `end_frame` (zero-based, at the document's rate, end exclusive).
- Each command family (`edit`, `process`, `markers`, `slices`, `playback` …) is one tool that takes the command's id and, where it takes one, its value. Every edit lands in the file's History, and `edit.undo` walks it back.
- For a folder (SoundEdit Pro): `library_open` it, then `library_query` with the Library's filter words or plain words ("short punchy kick", "quiet vocal loops at 120"). Stage a recipe and preview a row before anything is made; override a row that is wrong; then run it.
- A card's "unsure" marks a guess SoundEdit couldn't confirm by ear. Keep it out of names, tags and INFO, tell the person which sounds it couldn't identify, and give their answer to `library_teach`. Never teach your own guesses.
- A tool that writes files shows in SoundEdit's band and may wait for the person's Return there. With no window up, writes need the person's standing permission and folder access, and are refused without them.
- When a tool answers that it's SoundEdit Pro's, call `pro_trial`: SoundEdit asks the person, who decides. Never start a trial or buy for them.
