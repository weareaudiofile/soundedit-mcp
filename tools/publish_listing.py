#!/usr/bin/env python3
"""Keep this repository's listing equal to what the app itself serves.

The app's CI makes two files from the app's own code: tools.json (its MCP handshake identity, instructions and
tools/list, naming the app version that serves them) and the .mcpb (its Claude extension in the directory's form,
no one's token inside). It then runs this script in a fresh clone of this repository:

    python3 tools/publish_listing.py --export DIR              # say what would change; nothing is written back
    python3 tools/publish_listing.py --export DIR --keep       # and leave the files it would commit here
    python3 tools/publish_listing.py --export DIR --publish    # and publish it

When the tools, the instructions, the bridge script, the extension's manifest or the icon differ from what this
repository last published, --publish:

  1. writes glama/tools.json, the bridge's copies, the icons, the README's tools table, the plugin's version and
     server.json, and commits them;
  2. pushes, and makes the GitHub release v<version> with the .mcpb, then downloads it back and checks its SHA-256
     against server.json;
  3. publishes server.json to the official MCP Registry, last, because a registry version can't be taken back.

A run that stopped part way can be run again: until the registry has the version, every step is redone or kept.
Nothing is published when only the app's version moved.

Environment for --publish: GITHUB_LISTING_TOKEN (may push to this repository and make its releases) and
MCP_REGISTRY_KEY (the hex ed25519 key whose public half is in the registry domain's TXT record). MCP_PUBLISHER may
name an mcp-publisher binary; otherwise the pinned release is downloaded and checked. Python 3.9 or later, git, and
sips (macOS) for the icon's smaller sizes. The standard library only. Settings: tools/listing.json.
"""

import argparse
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
REGISTRY = "https://registry.modelcontextprotocol.io"
GITHUB_API = "https://api.github.com"
PUBLISHER = {
    "version": "1.8.9",
    ("Darwin", "arm64"): ("mcp-publisher_darwin_arm64.tar.gz",
                          "4175f7281c42ef2f6666d086974aa01f3eecd68a067cfb8329f0a7e620db6e3a"),
    ("Darwin", "x86_64"): ("mcp-publisher_darwin_amd64.tar.gz",
                           "f131bc753c293eb754cd183c2201013e0ed7f7a8ac0bd67dd2c4912f029029fd"),
}
VERSION = re.compile(r"^\d+\.\d+\.\d+$")


class Stop(Exception):
    """Why the run stops, in words for the job's log."""


def say(line=""):
    print(line, flush=True)


def path(*parts):
    return os.path.join(REPO, *parts)


def read_bytes(name):
    try:
        with open(path(name), "rb") as file:
            return file.read()
    except FileNotFoundError:
        return None


def write_bytes(name, data):
    os.makedirs(os.path.dirname(path(name)), exist_ok=True)
    with open(path(name), "wb") as file:
        file.write(data)


def read_json(name):
    with open(name if os.path.isabs(name) else path(name), encoding="utf-8") as file:
        return json.load(file)


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def version_key(version):
    return tuple(int(part) for part in version.split("."))


# MARK: - The web


def request(url, method="GET", data=None, headers=None, token=None):
    """(status, body). A token goes to the host asked, never on to a host it redirects to."""
    made = urllib.request.Request(url, data=data, method=method, headers=dict(headers or {}))
    made.add_header("User-Agent", "mcp-listing-sync")
    if token:
        made.add_unredirected_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(made, timeout=180) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def github(method, route, token, body=None, url=None, data=None, content_type=None):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        content_type = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    status, answer = request(url or GITHUB_API + route, method, data, headers, token)
    return status, (json.loads(answer) if answer and answer[:1] in (b"{", b"[") else answer)


def registry_entry(name, version):
    """The registry's entry for this version, or None."""
    route = "/v0/servers/%s/versions/%s" % (urllib.parse.quote(name, safe=""), urllib.parse.quote(version))
    status, body = request(REGISTRY + route)
    if status == 404:
        return None
    if status != 200:
        raise Stop("The registry answered %d for %s %s." % (status, name, version))
    entry = json.loads(body)
    return entry.get("server", entry)


# MARK: - The extension


class Extension:
    """A .mcpb file: its bytes and what is inside."""

    def __init__(self, data, origin):
        self.data = data
        self.sha = sha256(data)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                self.entries = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
            self.manifest = json.loads(self.entries["manifest.json"])
        except (zipfile.BadZipFile, KeyError, ValueError) as error:
            raise Stop("%s is not an extension: %s" % (origin, error))

    def differences(self, published):
        """What differs from the published extension, its version aside."""
        found = []
        if self.entries.get("server/index.js") != published.entries.get("server/index.js"):
            found.append("the bridge script")
        if self.entries.get("icon.png") != published.entries.get("icon.png"):
            found.append("the icon")
        mine, theirs = dict(self.manifest), dict(published.manifest)
        for manifest in (mine, theirs):
            manifest.pop("version", None)
        fields = sorted(key for key in set(mine) | set(theirs) if mine.get(key) != theirs.get(key))
        if fields:
            found.append("the extension's " + ", ".join(fields))
        extra = sorted((set(self.entries) ^ set(published.entries)) - {"icon.png"})
        if extra:
            found.append("the extension's files (%s)" % ", ".join(extra))
        return found


# MARK: - What changed


def tool_changes(listing, published):
    """What differs between the app's tools and the ones this repository lists."""
    old = {tool["name"]: tool for tool in published["tools"]}
    new = {tool["name"]: tool for tool in listing["tools"]}
    found = []
    added = [name for name in new if name not in old]
    gone = [name for name in old if name not in new]
    changed = [name for name in new if name in old and new[name] != old[name]]
    if added:
        found.append("new tools: " + ", ".join(added))
    if gone:
        found.append("tools gone: " + ", ".join(gone))
    if changed:
        found.append("tools changed: " + ", ".join(changed))
    if not (added or gone) and list(new) != list(old):
        found.append("the tools' order")
    if listing["instructions"] != published["instructions"]:
        found.append("the instructions")
    if listing["server"]["name"] != published["server"]["name"]:
        found.append("the server's name")
    return found


# MARK: - The repository's files


def tools_table(config, tools):
    """The README's tools table: written from the tools, or, for a table written by hand, checked against them."""
    table = config["toolsTable"]
    lines = read_bytes(table["file"]).decode("utf-8").split("\n")
    head = next((i for i, line in enumerate(lines) if line.startswith("| Tool |")), None)
    if head is None or not lines[head + 1].startswith("|---"):
        raise Stop("%s has no tools table (a line starting '| Tool |')." % table["file"])
    end = head + 2
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    rows = lines[head + 2:end]
    if table["mode"] == "check":
        named = set()
        for row in rows:
            first = row.split("|")[1]
            named.update(re.findall(r"`([A-Za-z0-9_]+)`", first))
        names = [tool["name"] for tool in tools]
        missing = [name for name in names if name not in named]
        stale = sorted(named - set(names))
        if missing or stale:
            raise Stop("%s's tools table is written by hand and no longer matches the tools: %s. Edit its rows, "
                       "commit, and run this again." % (table["file"], "; ".join(
                           (["no row for " + ", ".join(missing)] if missing else [])
                           + (["rows for tools gone: " + ", ".join(stale)] if stale else []))))
        return
    words = table["words"]

    def row(tool):
        hints = tool.get("annotations", {})
        kind = words["reads"] if hints.get("readOnlyHint") else (
            words["writes"] if hints.get("destructiveHint") else words["acts"])
        title = (tool.get("title") or tool["name"]).replace("|", "\\|")
        return "| `%s` | %s | %s |" % (tool["name"], title, kind)

    reads = [tool for tool in tools if tool.get("annotations", {}).get("readOnlyHint")]
    others = [tool for tool in tools if not tool.get("annotations", {}).get("readOnlyHint")]
    lines[head + 2:end] = [row(tool) for tool in reads + others]
    write_bytes(table["file"], "\n".join(lines).encode("utf-8"))


def prose_check(config, names_now, names_before):
    """No page may still name a tool the app no longer has."""
    gone = set(names_before) - set(names_now)
    if not gone:
        return
    stale = []
    for name in config["prose"]:
        text = read_bytes(name).decode("utf-8")
        if name == config["toolsTable"]["file"] and config["toolsTable"]["mode"] == "write":
            text = re.sub(r"(?m)^\| `[A-Za-z0-9_]+` \|.*$", "", text)
        for word in sorted(set(re.findall(r"`([A-Za-z0-9_]+)`", text)) & gone):
            stale.append("%s names `%s`" % (name, word))
    if stale:
        raise Stop("Tools are gone that these pages still name: %s. Edit them, commit, and run this again."
                   % "; ".join(stale))


def icons(config, icon):
    """The icon at full size, exactly as the app gave it, and its smaller sizes made from it."""
    if icon is None:
        raise Stop("The extension has no icon.png.")
    master = config["icon"]
    if read_bytes(master) == icon and all(read_bytes(name) is not None for name in config["iconSizes"]):
        return
    write_bytes(master, icon)
    if not shutil.which("sips"):
        raise Stop("Making the icon's smaller sizes needs sips (macOS).")
    for name, size in config["iconSizes"].items():
        os.makedirs(os.path.dirname(path(name)), exist_ok=True)
        subprocess.run(["sips", "-s", "format", "png", "-Z", str(size), path(master), "--out", path(name)],
                       check=True, stdout=subprocess.DEVNULL)


def write_files(config, version, listing, extension):
    app, repository = config["app"], config["repository"]
    tag = "v" + version
    write_bytes("glama/tools.json", json_bytes({
        "_about": "%s's tool definitions, as %s %s's own MCP server lists them. Read only by glama/stand-in.js "
                  "for Glama's build check." % (app, app, version),
        "server": {"name": listing["server"]["name"], "version": version},
        "instructions": listing["instructions"],
        "tools": listing["tools"],
    }))
    for name in config["bridges"]:
        write_bytes(name, extension.entries["server/index.js"])
    icons(config, extension.entries.get("icon.png"))
    tools_table(config, listing["tools"])

    plugin = read_json(config["plugin"])
    plugin["version"] = version
    write_bytes(config["plugin"], json_bytes(plugin))

    server = read_json("server.json")
    server["version"] = version
    raw = "https://raw.githubusercontent.com/%s/%s/" % (repository, tag)
    server["icons"] = [{"src": raw + name, "mimeType": "image/png", "sizes": ["%dx%d" % (size, size)]}
                       for name, size in config["registryIcons"].items()]
    for package in server["packages"]:
        if package.get("registryType") == "mcpb":
            package["identifier"] = "https://github.com/%s/releases/download/%s/%s" % (
                repository, tag, config["extension"])
            package["fileSha256"] = extension.sha
    write_bytes("server.json", json_bytes(server))


# MARK: - git


def git(*args, env=None, quiet=False):
    result = subprocess.run(["git", "-C", REPO] + list(args), env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        raise Stop("git %s failed:\n%s" % (args[0], result.stdout.strip()))
    if not quiet and result.stdout.strip():
        say(result.stdout.rstrip())
    return result.stdout.rstrip()


def ensure_fresh_clone():
    if git("status", "--porcelain", quiet=True):
        raise Stop("This clone has changes of its own; run in a clean clone of %s." % REPO)
    git("fetch", "--quiet", "origin", quiet=True)
    if git("rev-parse", "HEAD", quiet=True) != git("rev-parse", "origin/main", quiet=True):
        raise Stop("This clone isn't at origin/main; run in a fresh clone.")


def undo_changes():
    git("reset", "--quiet", "--hard", "HEAD", quiet=True)
    git("clean", "--quiet", "-fd", quiet=True)


def push(config, token):
    """Push main over HTTPS; the token reaches git through GIT_ASKPASS, never a command line."""
    folder = tempfile.mkdtemp()
    try:
        helper = os.path.join(folder, "askpass")
        with open(helper, "w") as file:
            file.write('#!/bin/sh\ncase "$1" in Username*) echo x-access-token ;; *) echo "$LISTING_PUSH_TOKEN" ;; '
                       "esac\n")
        os.chmod(helper, 0o700)
        env = dict(os.environ, GIT_ASKPASS=helper, GIT_TERMINAL_PROMPT="0", LISTING_PUSH_TOKEN=token)
        git("push", "--quiet", "https://github.com/%s.git" % config["repository"], "HEAD:refs/heads/main", env=env)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


# MARK: - The release


def release(config, version, commit, extension, notes, token):
    """Release v<version> at `commit` with the extension, then read the file back as anyone would."""
    route = "/repos/" + config["repository"]
    tag = "v" + version
    status, made = github("GET", route + "/releases/tags/" + tag, token)
    if status == 200:
        status, ref = github("GET", route + "/git/ref/tags/" + tag, token)
        target = ref.get("object", {}) if status == 200 else {}
        if target.get("type") == "tag":
            status, annotated = github("GET", route + "/git/tags/" + target["sha"], token)
            target = annotated.get("object", {})
        if target.get("sha") != commit:
            say("Release %s points elsewhere (an earlier run that stopped); making it again." % tag)
            github("DELETE", route + "/releases/%d" % made["id"], token)
            github("DELETE", route + "/git/refs/tags/" + tag, token)
            status = 404
    elif status != 404:
        raise Stop("GitHub answered %d for release %s." % (status, tag))
    if status == 404:
        status, made = github("POST", route + "/releases", token, body={
            "tag_name": tag, "target_commitish": commit, "name": tag, "body": notes, "make_latest": "true"})
        if status != 201:
            raise Stop("GitHub didn't make release %s (%d): %s" % (tag, status, made))
    else:
        github("PATCH", route + "/releases/%d" % made["id"], token, body={"body": notes, "make_latest": "true"})
    name = config["extension"]
    for asset in made.get("assets", []):
        if asset["name"] == name:
            github("DELETE", route + "/releases/assets/%d" % asset["id"], token)
    upload = made["upload_url"].split("{")[0] + "?name=" + urllib.parse.quote(name)
    status, answer = github("POST", None, token, url=upload, data=extension.data, content_type="application/zip")
    if status != 201:
        raise Stop("GitHub didn't take %s (%d): %s" % (name, status, answer))
    url = "https://github.com/%s/releases/download/%s/%s" % (config["repository"], tag, name)
    status, data = request(url)
    if status != 200 or sha256(data) != extension.sha:
        raise Stop("%s doesn't read back as the file uploaded (HTTP %d)." % (url, status))
    say("Released %s with %s (SHA-256 %s)." % (tag, name, extension.sha))


# MARK: - The registry


def publisher():
    named = os.environ.get("MCP_PUBLISHER")
    if named:
        return named
    key = (platform.system(), platform.machine())
    if key not in PUBLISHER:
        raise Stop("No pinned mcp-publisher for %s %s; set MCP_PUBLISHER." % key)
    asset, digest = PUBLISHER[key]
    folder = os.path.join(os.path.expanduser("~/.cache/mcp-publisher"), PUBLISHER["version"])
    binary = os.path.join(folder, "mcp-publisher")
    if os.path.exists(binary):
        return binary
    url = "https://github.com/modelcontextprotocol/registry/releases/download/v%s/%s" % (PUBLISHER["version"], asset)
    status, data = request(url)
    if status != 200 or sha256(data) != digest:
        raise Stop("mcp-publisher %s didn't download as pinned (HTTP %d)." % (PUBLISHER["version"], status))
    os.makedirs(folder, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        member = archive.getmember("mcp-publisher")
        with archive.extractfile(member) as source, open(binary + ".part", "wb") as target:
            shutil.copyfileobj(source, target)
    os.chmod(binary + ".part", 0o755)
    os.replace(binary + ".part", binary)
    return binary


def publish_registry(config, version, sha):
    key = os.environ.get("MCP_REGISTRY_KEY", "").strip()
    if not key:
        raise Stop("MCP_REGISTRY_KEY isn't set.")
    tool = publisher()
    home = tempfile.mkdtemp()  # the registry's login lands here, not in the runner's home
    try:
        env = dict(os.environ, HOME=home)
        for step, args in (("login", ["login", "dns", "--domain", config["registry"]["domain"], "--private-key", key]),
                           ("publish", ["publish"])):
            result = subprocess.run([tool] + args, cwd=REPO, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            output = result.stdout.replace(key, "[key]").strip()
            if result.returncode != 0:
                raise Stop("mcp-publisher %s failed:\n%s" % (step, output))
            say(output)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    entry = registry_entry(config["registry"]["name"], version)
    listed = [package.get("fileSha256") for package in (entry or {}).get("packages", [])]
    if sha not in listed:
        raise Stop("The registry doesn't list %s %s with this extension." % (config["registry"]["name"], version))
    say("The registry lists %s %s." % (config["registry"]["name"], version))


# MARK: - The run


def run(arguments):
    config = read_json(os.path.join(HERE, "listing.json"))
    app = config["app"]
    listing = read_json(os.path.abspath(os.path.join(arguments.export, "tools.json")))
    version = listing.get("server", {}).get("version", "")
    if not VERSION.match(version):
        raise Stop("tools.json names no version (server.version): %r" % version)
    with open(os.path.join(arguments.export, config["extension"]), "rb") as file:
        made = Extension(file.read(), config["extension"])
    env = made.manifest.get("server", {}).get("mcp_config", {}).get("env", {})
    if made.manifest.get("version") != version:
        raise Stop("%s names version %s, tools.json %s." % (config["extension"], made.manifest.get("version"), version))
    if env.get("AGENT_TOKEN") != "${user_config.token}" or "user_config" not in made.manifest:
        raise Stop("%s isn't the directory's form: it must ask for the token at install." % config["extension"])
    if made.manifest.get("name", "").lower() != listing["server"]["name"].lower():
        raise Stop("%s is %r, the tools %r." % (config["extension"], made.manifest.get("name"),
                                                listing["server"]["name"]))

    ensure_fresh_clone()
    server = read_json("server.json")
    published_version = server["version"]
    package = next(package for package in server["packages"] if package.get("registryType") == "mcpb")
    status, data = request(package["identifier"])
    published = None
    if status == 200 and sha256(data) == package["fileSha256"]:
        published = Extension(data, package["identifier"])
    elif status == 200:
        raise Stop("%s doesn't match server.json's SHA-256." % package["identifier"])
    in_glama = read_json("glama/tools.json")
    changes = tool_changes(listing, in_glama)
    changes += made.differences(published) if published else ["no published extension to compare (HTTP %d)" % status]

    name = config["registry"]["name"]
    if not changes:
        say("%s's listing is current: %s %s serves what %s %s lists." % (app, app, version, app, published_version))
        if registry_entry(name, published_version):
            return
        say("The registry doesn't list %s %s yet." % (name, published_version))
        if arguments.publish:
            publish_registry(config, published_version, package["fileSha256"])
        return

    say("%s %s's listing differs from %s's: %s." % (app, version, published_version, "; ".join(changes)))
    if version_key(version) < version_key(published_version):
        raise Stop("%s is older than the %s already listed." % (version, published_version))
    if registry_entry(name, version):
        raise Stop("The registry already has %s %s, and it can't be changed. The listing has to come from a later "
                   "%s version." % (name, version, app))
    prose_check(config, [tool["name"] for tool in listing["tools"]], [tool["name"] for tool in in_glama["tools"]])
    write_files(config, version, listing, made)
    say(git("status", "--short", quiet=True))
    if not arguments.publish:
        if arguments.keep:
            say("A dry run: the files are written here for a look, nothing committed or published.")
        else:
            say("A dry run: nothing committed or published (--publish does).")
            undo_changes()
        return

    token = os.environ.get("GITHUB_LISTING_TOKEN", "").strip()
    if not token:
        raise Stop("GITHUB_LISTING_TOKEN isn't set.")
    if git("status", "--porcelain", quiet=True):
        git("add", "--all", quiet=True)
        identity = config["committer"]
        git("-c", "user.name=" + identity["name"], "-c", "user.email=" + identity["email"], "commit", "--quiet",
            "-m", "%s %s's listing: %s" % (app, version, "; ".join(changes)), quiet=True)
        push(config, token)
    commit = git("rev-parse", "HEAD", quiet=True)
    notes = ("%s is the Claude desktop extension for %s, with no token inside. Open it and Claude asks for the token "
             "from %s ▸ Settings ▸ Agent, then keeps it in your Keychain.\n\n"
             "It lists the tools %s %s serves. Changed since %s: %s.\n\n"
             "Needs %s with Settings ▸ Agent turned on. When %s isn't running, the extension opens it with no window."
             "\n\nSHA-256: `%s`" % (config["extension"], app, app, app, version, published_version,
                                    "; ".join(changes), config["needs"], app, made.sha))
    release(config, version, commit, made, notes, token)
    publish_registry(config, version, made.sha)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--export", required=True, help="the folder with the app's tools.json and .mcpb")
    parser.add_argument("--publish", action="store_true", help="commit, push, release and publish to the registry")
    parser.add_argument("--keep", action="store_true", help="a dry run leaves what it wrote in this clone")
    try:
        run(parser.parse_args())
    except Stop as stop:
        say("Stopped: %s" % stop)
        sys.exit(1)


if __name__ == "__main__":
    main()
