# SoundEdit MCP server

<img src="assets/soundedit-icon-512.png" width="96" height="96" alt="SoundEdit">

Let the agent you already use work in [SoundEdit](https://audiofile.engineering/soundedit), an audio editor and sample manager for Mac, while you watch and listen. Your agent decides what to keep, what to call it and where it goes; SoundEdit does the listening and the work.

On the open file, the agent selects a range, then edits, processes, slices or marks it with the same commands your keys and menus run. Every edit lands in the file's History as yours would, so ⌘Z takes it back.

With SoundEdit Pro it also does what you do in the Library and the File menu: it opens folders and reads what SoundEdit measures about each sound (what it is, its tempo, note, key and loudness), finds sounds by what you describe or by how they sound, names, tags and files them, writes their tempo and root note into them, runs recipes, makes kits and multisamples for your sampler, fits files to a device, saves and exports.

The server is part of SoundEdit itself. This repository holds what an AI app needs to reach it: a Claude Desktop extension, a Claude Code plugin, and the setup for other MCP apps.

## What you need

- [SoundEdit for Mac](https://apps.apple.com/app/apple-store/id6761598947?pt=10877&ct=mcp-github&mt=8) 1.1 or later, on macOS 14 or later.
- SoundEdit ▸ Settings ▸ Agent ▸ **Let an agent drive SoundEdit** turned on. It's off until you turn it on, and the same page shows your token.
- The Library, recipe, kit and file tools are SoundEdit Pro's, and work during its free trial.

## Writing files

- Every call shows in SoundEdit's status band and lands in History.
- Anything that writes a file (a kit, a multisample, a fit to a device, a recipe run, a rename, a copy, a move, the Trash, Write Into Files or a save) goes ahead and shows in the band. Turn on Settings ▸ Agent ▸ **Wait for Return before the agent writes a file**, and each one waits there for your Return.
- With no window up, no one can press Return, so the agent's writes are refused unless you turn on **Let the agent write without asking**. That answer is kept for the token it was given under; a new token turns it off.
- Your AI app may also ask you before it runs a tool, as Claude Code and Claude Desktop do.

## Set it up

### Claude

Download `SoundEdit.mcpb` from the [latest release](https://github.com/weareaudiofile/soundedit-mcp/releases/latest), open it, and paste the token from SoundEdit's Settings ▸ Agent when Claude asks for it.

Or paste the `claude_desktop_config.json` entry from SoundEdit's Settings ▸ Agent (Claude ▸ Settings ▸ Developer ▸ Edit Config), then quit and reopen Claude.

When SoundEdit isn't running, the extension opens it with no window.

### Claude Code

Add this repository as a plugin marketplace and install the plugin. Claude Code asks for two settings: SoundEdit's address (keep `http://127.0.0.1:38411/mcp` unless you changed the port) and the token from SoundEdit's Settings ▸ Agent:

```text
/plugin install soundedit --marketplace weareaudiofile/soundedit-mcp
```

On Claude Code before 2.1.275, add the marketplace first:

```text
/plugin marketplace add weareaudiofile/soundedit-mcp
/plugin install soundedit@soundedit-mcp
```

Or run one line in Terminal; Settings ▸ Agent shows it with your token already in it:

```bash
claude mcp add --transport http soundedit http://127.0.0.1:38411/mcp --header "Authorization: Bearer YOUR_TOKEN"
```

### Codex

Add this to `~/.codex/config.toml`, then restart Codex:

```toml
[mcp_servers.soundedit]
url = "http://127.0.0.1:38411/mcp"
http_headers = { "Authorization" = "Bearer YOUR_TOKEN" }
```

### Other MCP apps

SoundEdit serves Streamable HTTP at `http://127.0.0.1:38411/mcp` and wants the header `Authorization: Bearer YOUR_TOKEN`. In an app that takes an `mcpServers` JSON file:

```json
{
  "mcpServers": {
    "soundedit": {
      "url": "http://127.0.0.1:38411/mcp",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}
```

If you change the port in Settings ▸ Agent, change it here too.

## Things to ask

On the open file:

- "Select the first half second and fade it in."
- "Normalize it to -1 dB peak."
- "Stretch this loop to 120 BPM."

With SoundEdit Pro:

- "Open my Samples folder and find the short punchy kicks."
- "Which sounds here are most like kick 03.wav?"
- "Split this recording of hits into takes and make an OP-XY kit."
- "Fit these files to my M8."
- "Run Clean one-shots on this folder."

## Tools

| Tool | What it does | Writes files |
|---|---|---|
| `get_state` | The open file: name, length, rate, channels, selection, markers, slices and History | no |
| `set_selection` | Select a range, in seconds or exact frames | no |
| one tool per command family: `edit`, `channels`, `process`, `tempo`, `knobs`, `playback`, `view`, `markers`, `slices`, `history`, `ingredients`, `slots`, `eq` | That family's commands on the open file, by id, with a value where one is taken. Each edit lands in History. | no |
| `file` (Pro) | Save the edit as a file of its own, save as, or export slices, marker regions or channels | yes |
| `file_facts` (Pro) | Measure files named by path and read each one's card | no |
| `library_open` (Pro) | Open folders in the Library, or a file in the editor | no |
| `library_query` (Pro) | Filter the Library by its own words or plain words, or by how a file sounds, and read each sound's card | no |
| `library_select` (Pro) | Select rows, as your clicks would | no |
| `library` (Pro) | The Library window's verbs: split a session, keep takes, stage clean one-shots, mix or append, hide copies, tempo ×2 or ÷2, undo | no |
| `library_set_info` (Pro) | Set INFO (tempo, key, root, loop, tags and more), kept with each sound | no |
| `library_command` (Pro) | Run the words you'd type in the Library's field: rename files, write INFO into them | yes |
| `library_files` (Pro) | Copy or move files into a folder, Copy as Heard, or move them to the Trash (never a hard delete) | yes |
| `library_split` (Pro) | Split a recording of many hits into named groups and takes | no |
| `library_teach` (Pro) | Teach the Library a class correction you made | its lessons only |
| `recipe_stage`, `recipe_preview`, `recipe_override` (Pro) | Stage a recipe on rows, hear a staged row, set one row's start, end, fade or gain | no |
| `recipe_run` (Pro) | Run the staged recipe, as ⌘⏎ does | when the recipe makes files |
| `deliver_kit` (Pro) | Make a kit for a sampler or device from a split session | yes |
| `fit_device` (Pro) | Fit files to a device's format, rate and length, into a new folder | yes |
| `make_multisample` (Pro) | Map notes by pitch, find each zone's loop, and make a multisample | yes |
| `pro_trial` | When a tool needs Pro, ask you for it in SoundEdit. It never starts the trial or buys. | no |
| `app_quit` | Quit SoundEdit when it runs with no window | no |

## What's in this repository

- `plugins/soundedit/`: the Claude Code plugin. It runs no code of its own: it connects Claude Code to SoundEdit at the address in its settings (`http://127.0.0.1:38411/mcp` unless you changed the port), with your token in the `Authorization` header.
- `server/index.js`: the script inside `SoundEdit.mcpb`, which Claude runs with its own Node. It hands each message to SoundEdit at 127.0.0.1 with your token and writes back SoundEdit's answer. When nothing answers, it opens SoundEdit with no window (`open -g -b engineering.audiofile.soundedit-macos --args -agent.headless YES`) and tries again for up to 45 seconds. It uses only Node's own modules.
- `server.json`: SoundEdit's entry in the official MCP Registry.
- `glama/`, `Dockerfile` and `glama.json`: for Glama's automated build check only. SoundEdit's server is part of the SoundEdit app, so Glama's Linux build machine runs `server/index.js` against a stand-in that lists SoundEdit's real tools (`glama/tools.json`, read from SoundEdit itself) and answers every call with a note to install SoundEdit. People never run these files.

## Privacy and security

- SoundEdit listens on 127.0.0.1 only. Nothing on your network or the internet can reach it.
- Only an app with the token from Settings ▸ Agent can connect. **New Token** there turns the old one away at once. A request from a web page is refused.
- The server answers only the AI app you set up. That app sends what it reads to its own AI service, under that app's terms.
- Audiofile's privacy policy: <https://audiofile.engineering/privacy>

## Support

Questions and problems: <https://audiofile.engineering/support>

## License

The files in this repository are under the MIT License. SoundEdit itself is Audiofile Engineering's app, on the Mac App Store.
