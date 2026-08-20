#!/usr/bin/env python3
"""Emits a context file as SessionStart additionalContext.

Standing instructions ship with the plugin rather than being pasted into each
person's CLAUDE.md, so an edit here reaches everyone on `/plugin update` instead
of needing each copy chased down. Python rather than sh + jq, so the hook runs on
every platform Claude Code does.

Every plugin that injects context carries its own byte-identical copy of this
file, and that is the correct shape rather than duplication to factor out. A
hook can only name files under its own `${CLAUDE_PLUGIN_ROOT}`: there is no
variable for a sibling plugin's root, the version stamp in that path makes one
unhardcodable, and each plugin has to stay independently installable. A
marketplace entry can declare that another plugin must be *enabled*, which is a
different thing — enablement grants no path to that plugin's files. A shared
file one level up does not ship — the install copies the plugin subtree alone —
and a symlink is worse still, since Windows refuses to create one without
developer mode, which is why the covered-endpoint scripts already fall back to
a shim. So the copies stay, and
what holds them together is a test rather than a shared file:
`test_every_copy_is_identical` compares each one and fails naming the file that
drifted. Edit this script in the repository — never in the installed tree — and
copy it over the others in the same change.
"""

import json
import sys
from pathlib import Path


def main(argv):
    if len(argv) != 1:
        return 0

    try:
        text = Path(argv[0]).read_text()

    except OSError:
        return 0

    # additionalContext is only honored nested under hookSpecificOutput; at the
    # top level (or as plain stdout) it reaches the debug log, not the model.
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": text,
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
