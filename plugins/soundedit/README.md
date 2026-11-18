# SoundEdit for Claude Code

![SoundEdit](assets/soundedit-icon-512.png)

Let Claude Code work in [SoundEdit](https://audiofile.engineering/soundedit), an audio editor and sample manager for Mac, while you watch and listen. This plugin adds SoundEdit's own MCP server and a skill that teaches Claude how to use it.

## What it runs and where it connects

The plugin runs one small Node.js script, `server/index.js`, the same bridge the SoundEdit extension for Claude Desktop runs. It uses only Node's own modules. It passes each message between Claude Code and SoundEdit at 127.0.0.1, on the port in its **SoundEdit port** option (38411 unless you changed it in SoundEdit ▸ Settings ▸ Agent), with the token from its **SoundEdit token** option in the `Authorization` header. When SoundEdit isn't running, it opens it with no window (`open -g -b engineering.audiofile.soundedit-macos --args -agent.headless YES`) and tries again for up to 45 seconds. It sends nothing anywhere else. Claude Code keeps the token in your system's secure storage.

## What you need

Node.js on your `PATH` for the bridge. SoundEdit for Mac 1.1 or later, with Settings ▸ Agent ▸ **Let an agent drive SoundEdit** turned on. The same page shows your token; paste it when Claude Code asks for it. The Library, recipe, kit and file tools are SoundEdit Pro's, and work during its free trial.

## Install

In Claude Code:

```text
/plugin install soundedit --marketplace weareaudiofile/soundedit-mcp
```

Claude Code asks for the token from SoundEdit's Settings ▸ Agent, and for SoundEdit's port (keep 38411 unless you changed it there).

## Things to ask

- "Select the first half second and fade it in."
- "Open my Samples folder and find the short punchy kicks."
- "Split this recording of hits into takes and make an OP-XY kit."

## What Claude can and can't do

On the open file, Claude selects, edits, processes, slices and marks, and every edit lands in History as yours would. With SoundEdit Pro it also does what you do in the Library and the File menu: names, tags, copies, moves or trashes sounds (never a hard delete), writes tempo and root notes into them, runs recipes and makes kits. Every call shows in SoundEdit's band, and Settings ▸ Agent can make each file write wait for your Return. What Claude reads goes to Anthropic as part of your conversation, under Claude's terms.

Privacy policy: <https://audiofile.engineering/privacy> · Support: <https://audiofile.engineering/support> · More: <https://github.com/weareaudiofile/soundedit-mcp>
