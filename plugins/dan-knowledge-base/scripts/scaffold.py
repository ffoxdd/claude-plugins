#!/usr/bin/env python3
"""Creates a knowledge base's directories, gitignore rules, register, and watermarks.

Idempotent and non-destructive by construction: every step either creates
something absent or reports that it left something alone. Re-running it on a
live knowledge base is a no-op that prints what it found, which is what makes it
safe to run when you are not sure whether a repo is set up.

`--dry-run` reports the same plan without writing, so `/dan-knowledge-base:init` can
show the user what will happen before it happens.

The one rule worth more than the rest is the gitignore entry. Everything else
here is convenience; that entry is what makes raw intake safe to pull in at all,
because it turns fetching something into an act with no publication
consequences. It is written before the inbox directory exists, so there is never
a window in which the directory is present and unignored.
"""

import argparse
import json
import sys
from pathlib import Path

CONFIG_FILENAME = ".knowledge-base.json"

GITIGNORE_RULES = """
# Raw intake stays local; only distilled notes are committed. This entry is what
# makes pulling a source into inbox/ safe — it is not a publication decision.
# `inbox/*` covers inbox/processed/ as well; the negation keeps the directory
# itself tracked so a fresh clone has somewhere to put intake.
inbox/*
!inbox/.gitkeep
""".lstrip()

GITIGNORE_SENTINEL = "inbox/*"

WATERMARKS = """\
# Watermarks for live sources. One line per source, updated after every sync.
#
# Record a watermark even when a source returned nothing, and say why it
# returned nothing — a quiet source and a broken query look identical here
# otherwise. A source deliberately skipped gets a line too.
#
# The format of each value is declared per source in .knowledge-base.json.
"""

REGISTER = {
    "layout": {
        "inbox": "inbox",
        "processed": "inbox/processed",
        "notes": "notes",
        "watermarks": "notes/.sync-state",
    },
    "sources": {},
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", default=".", help="repository to scaffold")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the plan without writing anything",
    )
    arguments = parser.parse_args(argv)

    root = Path(arguments.root).resolve()

    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 1

    actions = plan(root)

    for action, target, detail in actions:
        if action == "create" and not arguments.dry_run:
            apply_one(target, detail)

        verb = {"create": "would create" if arguments.dry_run else "created",
                "keep": "left alone"}[action]

        print(f"{verb}: {display(root, target)}" + (f" — {detail['note']}" if detail.get("note") else ""))

    if any(action == "keep" and target.name == CONFIG_FILENAME for action, target, _ in actions):
        print(f"\n{root / CONFIG_FILENAME} already exists — this repo is already a knowledge base.")

    return 0


def plan(root):
    """The ordered steps. Gitignore first, so no window exists in which inbox/
    is present and unignored."""
    steps = [
        (root / ".gitignore", {"kind": "gitignore"}),
        (root / "inbox" / ".gitkeep", {"kind": "empty", "note": "keeps a gitignored inbox/ tracked"}),
        (root / "inbox" / "processed", {"kind": "directory"}),
        (root / "notes", {"kind": "directory"}),
        (root / "notes" / ".sync-state", {"kind": "text", "body": WATERMARKS}),
        (root / CONFIG_FILENAME, {"kind": "json", "body": REGISTER,
                                  "note": "declares no sources yet"}),
    ]

    return [
        ("keep" if exists(target, detail) else "create", target, detail)
        for target, detail in steps
    ]


def exists(target, detail):
    if detail["kind"] == "gitignore":
        return target.is_file() and GITIGNORE_SENTINEL in target.read_text()

    return target.exists()


def apply_one(target, detail):
    kind = detail["kind"]

    if kind == "directory":
        target.mkdir(parents=True, exist_ok=True)
        return

    target.parent.mkdir(parents=True, exist_ok=True)

    if kind == "gitignore":
        # Append rather than replace: a repo that already has a gitignore has
        # rules worth more than this one.
        existing = target.read_text() if target.is_file() else ""
        separator = "" if not existing or existing.endswith("\n\n") else "\n"
        target.write_text(existing + separator + GITIGNORE_RULES)

    elif kind == "empty":
        target.touch()

    elif kind == "text":
        target.write_text(detail["body"])

    elif kind == "json":
        target.write_text(json.dumps(detail["body"], indent=2) + "\n")


def display(root, target):
    try:
        return str(target.relative_to(root))

    except ValueError:
        return str(target)


if __name__ == "__main__":
    sys.exit(main())
