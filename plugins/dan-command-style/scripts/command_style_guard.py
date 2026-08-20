#!/usr/bin/env python3
"""Denies Bash invocations that defeat the permission allowlist.

The pattern below is correct-but-costly: the command would work, and would
raise an approval prompt a person has to clear. Denying with the replacement
in the reason turns a prompt into a retry.

Exit status is always 0; the decision travels in the JSON on stdout.
"""

import json
import re
import sys

CD_THEN_GIT = re.compile(r"(?:^|&&|;|\|)\s*cd\s[^&;|]*(?:&&|;)\s*git\b")

CD_THEN_GIT_REASON = (
    "Use `git -C <dir> ...` instead of `cd <dir> && git ...` — the cd triggers "
    "the untrusted-hooks prompt and defeats the Bash(git *) allowlist."
)


def main():
    command = read_command()

    if not command:
        return

    if CD_THEN_GIT.search(command):
        deny(CD_THEN_GIT_REASON)


def read_command():
    try:
        payload = json.load(sys.stdin)

    except (json.JSONDecodeError, ValueError):
        return ""

    return payload.get("tool_input", {}).get("command", "")


def deny(reason):
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    try:
        main()

    except Exception:
        pass

    sys.exit(0)
