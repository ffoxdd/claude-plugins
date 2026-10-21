#!/usr/bin/env python3
"""Sets the spawn guard's limits for one session, on the person's instruction.

The guard's limits are plugin options, the default for every session. A grant
decides one session: a person who wants three reviews side by side this
afternoon writes one, a small JSON file beside the session's pending approvals
under the plugin's data directory, which the guard reads ahead of the options.
It is keyed by session id, so it is inert once that session ends.

Invoked by `/dan-work-routing:session-limits`, whose body substitutes the data
directory (`${CLAUDE_PLUGIN_DATA}` resolves in command Markdown but is not in
the Bash tool's environment). The session id comes from `CLAUDE_CODE_SESSION_ID`,
which Claude Code exports to the Bash tool, or from `--session`. Arguments are
`key=value` pairs in the option vocabulary (`top_tier_concurrency=3`, 0 lifts
the limit), `reset` to remove the grant, or nothing to print it.

This is a person's decision. A denial from the guard is answered by waiting or
folding, never by running this.
"""

import argparse
import json
import os
import sys
import time

# The guard owns the grant's location and shape; this script only writes it.
from agent_spawn_guard import DEFAULTS, grant_path, read_grant

OPTION_KEYS = tuple(key.lower() for key in DEFAULTS)


def main(argv):
    parser = argparse.ArgumentParser(
        description="Set the spawn guard's limits for this session alone.",
    )
    parser.add_argument(
        "--data",
        required=True,
        help="the plugin's data directory, ${CLAUDE_PLUGIN_DATA}",
    )
    parser.add_argument(
        "--session",
        default=os.environ.get("CLAUDE_CODE_SESSION_ID"),
        help="the session id; defaults to CLAUDE_CODE_SESSION_ID",
    )
    parser.add_argument(
        "settings",
        nargs="*",
        metavar="KEY=VALUE | reset",
        help=f"one of {', '.join(OPTION_KEYS)}, with a non-negative integer; 0 lifts the limit",
    )
    arguments = parser.parse_args(argv)

    if not arguments.session:
        parser.error("no session id: CLAUDE_CODE_SESSION_ID is not set, so pass --session <id>")

    path = grant_path(arguments.session, arguments.data)

    if arguments.settings == ["reset"]:
        remove(path)
        print("Grant removed; the plugin options apply to this session again.")
        return 0

    if not arguments.settings:
        print(describe(read_grant(path)))
        return 0

    changes = parse(arguments.settings, parser)
    granted = {**read_grant(path), **changes}
    write(path, granted)
    print(describe(granted))
    return 0


def parse(settings, parser):
    changes = {}

    for setting in settings:
        key, separator, value = setting.partition("=")

        if not separator or key not in OPTION_KEYS:
            parser.error(
                f"'{setting}' is not KEY=VALUE with KEY one of {', '.join(OPTION_KEYS)}"
            )

        if not value.isdigit():
            parser.error(f"'{setting}': the value must be a non-negative integer; 0 lifts the limit")

        changes[key] = int(value)

    return changes


def write(path, granted):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"limits": granted, "granted_at": time.time()}, indent=2) + "\n",
        encoding="utf-8",
    )


def remove(path):
    try:
        path.unlink()

    except FileNotFoundError:
        pass


def describe(granted):
    if not granted:
        return "No grant for this session; the plugin options apply."

    lines = ["This session's grant, read ahead of the plugin options:"]

    for key, value in granted.items():
        lines.append(f"  {key}={value}" + ("  (lifted)" if value == 0 else ""))

    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
