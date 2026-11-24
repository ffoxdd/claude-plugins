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

Bounded the same way the sibling grants in this marketplace are: shlex tokenizes
the command, and any shell operator disqualifies it, so an approved first word
cannot carry a second command. A settings `deny` still overrides this — measured,
not assumed — as does a `deny` from any other hook.

Exit status is always 0; the decision travels in the JSON on stdout. Silence means
the ordinary prompt, and so does a crash: there is no blanket except here, because
writing nothing is the safe answer for a grant.
"""

import json
import shlex
import sys

COMMAND = "slack-client"

APPROVED_SUBCOMMANDS = ("channels", "starred", "memberships")

# Shell operators shlex hands back as their own tokens.
OPERATORS = (";", "|", "||", "&", "&&", ">", ">>", "<", "(", ")")

# The two shlex does not surface as operators: a backtick is an ordinary word
# character to it, and a bare newline is whitespace, so a second command carried
# by either survives the operator check — a newline even smuggles a second
# `slack-client login` past the exclusion below, since only the first subcommand
# is inspected. Refuse both.
SUBSTITUTION_OR_NEWLINE = ("`", "\n", "\r")

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
    if any(character in command for character in SUBSTITUTION_OR_NEWLINE):
        return False

    tokens = tokenize(command)

    if len(tokens) < 2 or tokens[0] != COMMAND:
        return False

    if any(token in OPERATORS for token in tokens):
        return False

    # The subcommand is argparse's first positional, so it is the first token that
    # is not a flag — matching on position alone would miss `slack-client --help
    # memberships` and approve nothing that argparse would accept.
    return next((token for token in tokens[1:] if not token.startswith("-")), "") in (
        APPROVED_SUBCOMMANDS
    )


def tokenize(command):
    """A command shlex cannot parse — an unclosed quote — is one for a person to
    read, not one to approve on a guess about where it ends."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True

        return list(lexer)

    except ValueError:
        return []


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
