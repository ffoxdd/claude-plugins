#!/usr/bin/env python3
"""Checks the prerequisites of the sources this knowledge base declares.

Runs at SessionStart, and does nothing at all unless the working directory is
inside a knowledge base. That gate is not politeness: this plugin ships a Slack
client and a mail sweep, and a session working on unrelated code has no use for
either. Config discovery already answers "am I in a knowledge base?", so the
same walk up the tree that finds the register decides whether to speak.

Within one, **every check is derived from the register** — the sources declared
in .knowledge-base.json — and never from what the plugin happens to ship. A
knowledge base that only processes files dropped into inbox/ by hand declares no
adapters, needs nothing installed, and is told nothing. Verifying a stated
requirement is the job; inventing one is how a plugin becomes something people
disable.

It installs nothing. `slack-client` ships in the plugin's own bin/, which Claude
Code puts on PATH for every installed plugin, so it resolves by name in the
session that runs `slack-client login` — with nothing written into $HOME and
nothing to re-point when the version-stamped plugin root changes.

Exit status is always 0; a failed check is a message, not a broken session.
"""

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import configuration

# What each adapter needs beyond what this plugin ships: the shipped commands it
# runs, so a shadowed one is caught, and the tools the plugin cannot supply at all.
# Keyed by the `adapter` value in a register entry.
ADAPTER_REQUIREMENTS = {
    "chat": {
        "scripts": ("slack-client",),
        "commands": ("uv",),
    },
    "email": {
        "scripts": (),
        "commands": ("uv",),
    },
}

# Names an earlier version symlinked into ~/.local/bin. Transitional: delete this
# and clear_superseded_links once every install has started at least once on a
# version that ships bin/.
SUPERSEDED_LINKS = ("slack-client",)


def main():
    plugin_root = Path(__file__).resolve().parent.parent

    try:
        document, root = configuration.load()

    except configuration.ConfigurationError as error:
        # Outside a knowledge base this is the ordinary case and must stay
        # silent. Inside one, a register that will not parse is worth saying
        # once — a sync would otherwise report having swept nothing.
        report_broken_register(error)
        return

    adapters = declared_adapters(document)

    if not adapters:
        return

    cleanups = clear_superseded_links()

    notes = []
    notes.extend(check_shipped_scripts(plugin_root, adapters))
    notes.extend(check_commands(adapters))
    notes.extend(check_interactive_setup(adapters, root, document))

    if notes:
        notes.append("run /dan-knowledge-base:setup for a guided fix.")

    if cleanups or notes:
        report(cleanups + notes)


def report_broken_register(error):
    if configuration.find() is None and not os.environ.get("KNOWLEDGE_BASE_CONFIG_FILE"):
        return

    report([str(error)])


def declared_adapters(document):
    """The adapter names this knowledge base declares, ignoring sources the model
    queries directly (adapter null) — those need nothing from this plugin."""
    return sorted(
        {
            entry.get("adapter")
            for entry in document.get("sources", {}).values()
            if isinstance(entry, dict) and entry.get("adapter") in ADAPTER_REQUIREMENTS
        }
    )


def clear_superseded_links():
    """Removes the ~/.local/bin links an earlier version of this plugin installed.

    They would otherwise outrank the plugin's own bin/ on most PATHs while pointing
    into a cache directory the next update deletes. Only a symlink into a plugin
    cache is removed, which is only ever one this plugin created; a real file, or a
    link into someone's own tree, is theirs and is left alone — and reported by
    check_shipped_scripts if it shadows a command this knowledge base needs.
    """
    return [
        remove_link(link)
        for link in (Path.home() / ".local" / "bin" / name for name in SUPERSEDED_LINKS)
        if link.is_symlink() and is_plugin_owned(Path(os.readlink(link)))
    ]


def remove_link(link):
    link.unlink()

    return (
        f"removed {link}, a leftover link from an earlier version — the plugin's own "
        "bin/ is on PATH now, so nothing is installed into your home directory."
    )


def is_plugin_owned(target):
    return "plugins" in target.parts and target.name in SUPERSEDED_LINKS


def check_shipped_scripts(plugin_root, adapters):
    """Whether the commands this plugin ships resolve to *this* copy.

    Resolving to something else is the failure worth catching: a same-named script
    in someone's own tree silently substitutes itself, and the symptom appears later
    as an adapter behaving unlike its documentation. Resolving to nothing is not
    reported, because this hook's environment is not the environment the Bash tool
    runs commands in — the plugin bin/ entry can be absent here and present there.
    """
    return [
        note
        for adapter in adapters
        for name in ADAPTER_REQUIREMENTS[adapter]["scripts"]
        for note in check_one_shipped_script(plugin_root / "bin" / name)
    ]


def check_one_shipped_script(launcher):
    if not launcher.exists():
        return [f"{launcher.name} is missing from the plugin — reinstall it."]

    resolved = shutil.which(launcher.name)

    if not resolved or same_file(Path(resolved), launcher):
        return []

    return [
        f"{resolved} shadows the plugin's {launcher.name} at {launcher}: "
        "remove it, or the adapter runs something other than this plugin"
    ]


def same_file(left, right):
    try:
        return left.samefile(right)

    except OSError:
        return False


def check_commands(adapters):
    """Tools the plugin cannot ship, named per adapter so the note says which
    source stops working rather than leaving that to be inferred."""
    notes = []

    for adapter in adapters:
        for command in ADAPTER_REQUIREMENTS[adapter]["commands"]:
            if not shutil.which(command):
                notes.append(
                    f"'{command}' is not installed, and the {adapter} adapter runs on it. "
                    f"Until it is, skip that source and note the skip in the watermarks."
                )

    return notes


def check_interactive_setup(adapters, root, document):
    """The one-time steps only a person can do, each reported once.

    These are deliberately separated from missing tools: the remedy is an
    interactive login at a terminal, not an install, and a report that mixes the
    two leaves the reader to work out which is which.
    """
    notes = []

    if "chat" in adapters and not chat_session_captured():
        notes.append(
            "no captured Slack session, so the chat adapter cannot read anything: "
            "run `slack-client login` once (it opens a real browser), and "
            "`uv run --with playwright playwright install chromium` first if that fails."
        )

    if "email" in adapters and not mail_credential_cache_present(document):
        notes.append(
            "no mail credential cache found, so the email adapter cannot authenticate: "
            "sign in through the mail MCP server once, and check the register names "
            "the right tenant."
        )

    return notes


def chat_session_captured():
    return (Path.home() / ".cache" / "slack-client" / "session.json").is_file()


def mail_credential_cache_present(document):
    """The mail adapter borrows a mail MCP server's own token cache rather than
    minting a credential. The register may name where that cache lives, since the
    location moves when that server updates; the default is where current
    versions write it."""
    configured = document.get("sources", {}).get("email", {}).get("credential_cache")

    if configured:
        return Path(configured).expanduser().is_file()

    default = Path.home() / ".config" / "ms-365-mcp-server" / "msal-token-cache.json"

    if default.is_file():
        return True

    # macOS-only fallback, and stated as such: older versions kept the cache in
    # the login keychain. On Windows and Linux there is no keychain to check, so
    # the absence of the file is the whole answer and the note must not send a
    # reader looking for one.
    return sys.platform == "darwin" and keychain_holds_cache()


def keychain_holds_cache():
    import subprocess

    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "ms-365-mcp-server"],
            capture_output=True,
        )

    except OSError:
        return False

    return result.returncode == 0


def report(notes):
    body = "dan-knowledge-base: " + "; ".join(notes)

    json.dump(
        {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": body}},
        sys.stdout,
    )


if __name__ == "__main__":
    try:
        main()

    except Exception:
        # A provisioner that breaks a session start is worse than one that fails
        # to provision. Never propagate.
        pass

    sys.exit(0)
