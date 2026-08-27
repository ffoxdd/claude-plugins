#!/usr/bin/env python3
"""Approves the reads `slack-client` exists to do, so a sync needs no allowlist entry.

Every intake run reaches Slack through this command, and until now each call was a
permission prompt — which made a plugin whose whole purpose is an unattended sweep
depend on someone sitting there approving it. Installing the plugin is the grant.

`login` is deliberately not approved. It opens a real browser and waits up to five
minutes for a person to sign in, so it is the one subcommand a person runs rather
than Claude; approving it would let an unattended sync launch a browser and hang on
it. Everything else here reads: channels, starred, memberships, history, replies.

That split is not a safety compromise — the reads are the entire adapter, and the
captured session they use is as sensitive as a Slack login either way. Approving
them changes who has to be present, not what the command can see.

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

APPROVED_SUBCOMMANDS = ("channels", "starred", "memberships", "history", "replies")

# Shell operators shlex hands back as their own tokens.
OPERATORS = (";", "|", "||", "&", "&&", ">", ">>", "<", "(", ")")

# The two shlex does not surface as operators: a backtick is an ordinary word
# character to it, and a bare newline is whitespace, so a second command carried
# by either survives the operator check — a newline even smuggles a second
# `slack-client login` past the exclusion below, since only the first subcommand
# is inspected. Refuse both.
SUBSTITUTION_OR_NEWLINE = ("`", "\n", "\r")

REASON = (
    "A read-only slack-client call, with no way to reach a second command. "
    "Approved by the dan-knowledge-base plugin, whose installation is the grant. "
    "`slack-client login` is not approved: a person runs that one."
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
    # history` and approve nothing that argparse would accept.
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
