#!/usr/bin/env python3
"""Approves the `slack-client` listings a session runs, so setup needs no allowlist entry.

Installing the plugin is the grant, and it covers the metadata subcommands only:
`channels`, `starred` and `memberships`, which print conversation ids, names,
lock flags and topics. Those are what a person checks while setting a source up,
and none of them prints a message.

`history` and `replies` are not approved. They print message text to whoever ran
them, and a session that runs one reads raw chat with no gate in between. The
chat adapter calls the client as a subprocess and writes what it reads under the
intake directory, so it needs neither approved; a person who wants raw history
in a session answers the ordinary prompt.

`login` is not approved either. It opens a real browser and waits up to five
minutes for a person to sign in, so it is the one subcommand a person runs rather
than Claude; approving it would let an unattended sync launch a browser and hang on
it. Nor is `file`: it writes a local path of the caller's choosing, and where bytes
land is a decision a person keeps.

**It approves only what it can read exactly as the shell will.** A list of
forbidden characters is the wrong shape for a grant: whatever it forgets, the
shell still runs. `shlex`, for one, drops everything after a `#` inside a word,
where bash and zsh read `x#` as a literal, so `slack-client channels x# ; id`
looked like one harmless command. So the rule is inverted:

  * every character of the command is one of ASCII letters, digits, the space,
    `_`, `,`, `=` and `-` — enough for every option the listings take, and none
    of the characters any bash or zsh expansion starts from (brace, tilde,
    parameter, command, arithmetic, process substitution, filename generation and
    its zsh qualifiers, history, and `=` expansion, which only a word's first
    character can trigger, and no word may start with `=`). With no expansion,
    there is no word splitting either, and with no quote, no tab and no newline,
    splitting at spaces gives the shell's own words;
  * every word after `slack-client` is a lower-case word or a flag
    (`--types`, `--types=all`, `-h`), and no word starts with `=`;
  * the first word that is not a flag, argparse's subcommand, is a listing.

Anything else is left to the ordinary prompt. A settings `deny` still overrides
this — measured, not assumed — as does a `deny` from any other hook.

Exit status is always 0; the decision travels in the JSON on stdout. Silence means
the ordinary prompt, and so does a crash: there is no blanket except here, because
writing nothing is the safe answer for a grant.
"""

import json
import re
import string
import sys

COMMAND = "slack-client"

APPROVED_SUBCOMMANDS = ("channels", "starred", "memberships")

# Every character a listing needs, and none a shell expands or splits on.
ALLOWED_CHARACTERS = frozenset(string.ascii_letters + string.digits + " _,=-")

# A subcommand or an option's value: `channels`, `public_channel,im`.
WORD = re.compile(r"[a-z_,]+")

# An option, with its value attached or not: `-h`, `--types`, `--types=all`.
FLAG = re.compile(r"--?[a-z][a-z-]*(=[a-z_,]+)?")

REASON = (
    "A slack-client listing that prints no message, with no way to reach a second "
    "command. Approved by the dan-knowledge-base plugin, whose installation is the "
    "grant. `history`, `replies`, `file` and `login` are not approved."
)


def main():
    command = read_command()

    if not command or not approves(command):
        return

    allow(REASON)


def approves(command):
    if not set(command) <= ALLOWED_CHARACTERS:
        return False

    # Within those characters the shell's words are exactly the space-separated
    # runs: no quote, no escape, no expansion, nothing that starts a comment.
    tokens = [token for token in command.split(" ") if token]

    if len(tokens) < 2 or tokens[0] != COMMAND:
        return False

    if not all(WORD.fullmatch(token) or FLAG.fullmatch(token) for token in tokens[1:]):
        return False

    # The subcommand is argparse's first positional, so it is the first token that
    # is not a flag — matching on position alone would miss `slack-client --help
    # memberships` and approve nothing that argparse would accept.
    return next((token for token in tokens[1:] if not token.startswith("-")), "") in (
        APPROVED_SUBCOMMANDS
    )


def read_command():
    try:
        # Claude Code writes the payload as UTF-8; left to the locale, a Windows
        # Python would read it as the code page and garble every non-ASCII character.
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        payload = json.load(sys.stdin)

    except (json.JSONDecodeError, ValueError):
        return ""

    return payload.get("tool_input", {}).get("command", "")


def allow(reason):
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
    sys.exit(0)
