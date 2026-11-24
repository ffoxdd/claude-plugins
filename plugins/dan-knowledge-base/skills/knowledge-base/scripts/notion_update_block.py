#!/usr/bin/env python3
"""Update one Notion block from a JSON body file, over the REST API.

The Notion MCP server's `update-a-block` tool cannot send most block updates: it
takes the update under a parameter named `type` and posts it nested there, so
Notion receives no `table_row`, `paragraph` or other type key at the top of the
body and refuses it with a list of every block type it expected. A table row (a
person's row in a weekly team table, say) has no other edit route.

This sends the body as written, with the credential the other Notion scripts use
(the MCP server's own token, read from Claude Code's config):

    python3 <SKILL_DIR>/scripts/notion_update_block.py <block id> <body.json>

The body file is exactly what `PATCH /v1/blocks/{id}` takes, for example a table
row, whose `cells` must list every column, an empty list for a blank cell:

    {"table_row": {"cells": [[{"type": "text", "text": {"content": "Dan"}}], [], ...]}}

Find a row's id by listing the table block's children. Updating replaces the
whole row, so read it first and carry over any cell being left alone.

It prints the status and the length of each updated cell or rich-text field, never
the text, so the output can't echo what it wrote or what the block held.

Exit status: 0 updated; 1 refused or failed.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import notion_credential
from notion_api import DEFAULT_API_BASE, EXIT_REFUSED, ExportError, Notion


def text_lengths(block):
    """Character counts of the block's text, by cell for a table row."""
    content = block.get(block.get("type"), {})

    if "cells" in content:
        return [sum(len(part.get("plain_text", "")) for part in cell) for cell in content["cells"]]

    return [sum(len(part.get("plain_text", "")) for part in content.get("rich_text", []))]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("block_id", help="the block to update")
    parser.add_argument("body", help="JSON file holding the PATCH body")
    arguments = parser.parse_args(argv)

    try:
        body = json.loads(Path(arguments.body).read_text(encoding="utf-8"))
        notion = Notion(DEFAULT_API_BASE, notion_credential.authorization({}))

    except (OSError, json.JSONDecodeError, notion_credential.CredentialError) as error:
        print(f"notion_update_block: {type(error).__name__}: {error}", file=sys.stderr)

        return EXIT_REFUSED

    try:
        block = notion.request("PATCH", f"/blocks/{arguments.block_id}", body)

    except ExportError as error:
        print(f"notion_update_block: {error}", file=sys.stderr)

        return EXIT_REFUSED

    print(f"updated {block.get('type')} {arguments.block_id}: text lengths {text_lengths(block)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
