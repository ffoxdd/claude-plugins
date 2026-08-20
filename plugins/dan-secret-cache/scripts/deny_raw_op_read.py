#!/usr/bin/env python3
"""Refuses `op read` in favour of get-secret, which caches what op re-prompts for.

The rule binds only where the alternative exists: without get-secret on PATH there is
nothing to redirect to, and denying would leave no way to read a secret at all. Discovery
(`op item get`, `op item list`) is untouched — it has no cached form and is a first-time
cost worth paying.
"""

import json
import re
import shutil
import sys

# `op` as a command rather than as a word: at the start, or after a pipe, semicolon,
# ampersand, or an opening command substitution. `op read` inside a quoted string is
# somebody's documentation, not an invocation.
RAW_READ = re.compile(r"(?:^|[|;&]|\$\()\s*op\s+read\s")

REASON = (
    "Use `get-secret <op-reference>` rather than `op read`. It answers from the login "
    "keychain, so 1Password approves once per secret instead of once per call — and each "
    "call it saves is an approval raised on the desktop that this session cannot see. "
    "Discovery (`op item list`, `op item get`) is unaffected, and get-secret wraps the one "
    "`op read` that belongs."
)


def main():
    try:
        command = json.load(sys.stdin).get("tool_input", {}).get("command", "")

    except (json.JSONDecodeError, AttributeError):
        return 0

    if not RAW_READ.search(command) or not shutil.which("get-secret"):
        return 0

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": REASON,
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
