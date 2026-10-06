#!/usr/bin/env python3
"""Print the blocks of one Notion page edited since a watermark, with their
ancestors for context and any comments left on them since.

The page-changes tool, for the session's own reading. The sweep manifest names
a page that changed; fetching it whole through the MCP server returns every
block it has ever held, and on a page written into weekly that is a year of
agendas, image URLs included, to read one new section. This prints the new
section instead:

  * a block is **printed when it was edited at or after the watermark**, in
    full, with its own edited descendants below it;
  * an unchanged ancestor is printed as **one line of context**, marked as such,
    so a new bullet still reads under its heading;
  * an unchanged block that is nobody's ancestor is not printed at all;
  * **comments** created since the watermark are printed under the block they
    sit on, with the author's name. The page's own comments come first. Comments
    are fetched for the page and for every block, because leaving one changes
    nothing about the block;
  * images and files are named, never linked: a signed file URL is a few
    hundred characters that say nothing.

**It refuses a page under a covered location**, or one it cannot place, and
prints nothing of it. The `notion` adapter is the route for those, through the
isolated agent. A page is placed the way the sweep places it, by parent chain
against the register's covered locations (`notion_search.py`), so a page the
sweep listed by title is one this will print. That is what keeps this tool from
becoming a way around the covered route: it reads the same register and draws
the same line.

Output is stdout, and unlike the adapters it carries content: that is its
purpose, and the refusal above is what makes it safe to run from a session.

    python3 notion_page_changes.py <page id> <watermark> [--source notion]

Exit status: 0 printed; 1 refused, before any content is printed.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import configuration
import notion_credential
import notion_search
from notion_api import EXIT_REFUSED, ExportError, Notion, created_since, edited_since, \
    format_time, parse_time, read_watermark
from notion_export import DEFAULT_MAX_BLOCK_NESTING, PAGE_BLOCK_TYPES, indent_lines, \
    page_title, plain_text, render_block

CONTEXT_WIDTH = 120


class Refused(Exception):
    """Why nothing of the page is printed."""


class Node:
    """A block, its children, and whether anything here changed."""

    def __init__(self, block, since, children):
        self.block = block
        self.children = children
        self.changed = edited_since(block, since)
        self.comments = []

    @property
    def included(self):
        return self.changed or any(child.included for child in self.children)


def block_tree(notion, block_id, since, nesting=0):
    nodes = []

    for block in notion.children(block_id):
        children = []

        if block.get("has_children") and block["type"] not in PAGE_BLOCK_TYPES:
            if nesting < DEFAULT_MAX_BLOCK_NESTING:
                children = block_tree(notion, block["id"], since, nesting + 1)

        nodes.append(Node(block, since, children))

    return nodes


class Authors:
    """Comment authors by id, each looked up once. A user the integration cannot
    see keeps its id."""

    def __init__(self, notion):
        self.notion = notion
        self.names = {}

    def name(self, user):
        identifier = user.get("id", "")

        if identifier not in self.names:
            try:
                self.names[identifier] = self.notion.user(identifier).get("name") or identifier

            except ExportError:
                self.names[identifier] = identifier

        return self.names[identifier]


def comments_since(notion, block_id, since):
    try:
        return [comment for comment in notion.comments(block_id) if created_since(comment, since)]

    except ExportError:
        return []


def attach_comments(notion, nodes, since):
    """Every block is asked, changed or not: a comment does not edit its block."""
    for node in nodes:
        node.comments = comments_since(notion, node.block["id"], since)
        attach_comments(notion, node.children, since)


def render_comment(comment, authors):
    return (f"> 💬 {authors.name(comment.get('created_by') or {})}, "
            f"{format_time(parse_time(comment['created_time']))}: "
            f"{plain_text(comment.get('rich_text'))}")


def context_line(rendered):
    first = rendered.split("\n", 1)[0]

    if len(first) > CONTEXT_WIDTH:
        first = first[:CONTEXT_WIDTH].rstrip() + "…"

    return f"{first} *(unchanged, for context)*"


def render_nodes(nodes, authors, depth=0):
    lines = []

    for node in nodes:
        if not node.included and not node.comments:
            continue

        rendered = render_block(node.block) or "*(empty block)*"

        if not node.changed:
            rendered = context_line(rendered)

        lines.append(indent_lines(rendered, depth))
        lines += [indent_lines(render_comment(comment, authors), depth) for comment in node.comments]
        lines += render_nodes(node.children, authors, depth + 1)

    return lines


def count_changed(nodes):
    return sum((1 if node.changed else 0) + count_changed(node.children) for node in nodes)


def count_comments(nodes):
    return sum(len(node.comments) + count_comments(node.children) for node in nodes)


def place(notion, locations, page):
    try:
        location = notion_search.Placement(notion, locations).location_of(page)

    except notion_search.Unplaceable as error:
        raise Refused(f"page {page['id']} could not be placed ({error}); it might sit under a "
                      "covered location, so nothing of it is printed") from None

    if location is not None:
        raise Refused(f"page {page['id']} is under the covered location {location!r}; the notion "
                      "adapter reads it, through the isolated agent")


def fetch_page(notion, page_id):
    try:
        return notion.page(page_id)

    except ExportError as error:
        raise Refused(f"page {page_id} could not be read ({error})") from None


def report(notion, page, since):
    nodes = block_tree(notion, page["id"], since)
    attach_comments(notion, nodes, since)
    authors = Authors(notion)
    page_comments = comments_since(notion, page["id"], since)

    lines = [
        f"# {page_title(page)} — changes since {format_time(since)}",
        "",
        f"*Page `{page['id']}`, last edited {page['last_edited_time']}. Blocks edited since the "
        "watermark, with unchanged ancestors for context; comments left since the watermark "
        "under the blocks they sit on.*",
        "",
    ]
    lines += [render_comment(comment, authors) for comment in page_comments]
    lines += render_nodes(nodes, authors)

    changed = count_changed(nodes)
    comments = len(page_comments) + count_comments(nodes)

    if not changed and not comments:
        lines.append("No block edited and no comment left since the watermark. The page's own "
                     "edit time moved, so a property or something this does not read changed.")

    lines += ["", f"*{changed} changed block(s), {comments} comment(s).*"]

    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("page_id", help="the page, as the sweep manifest names it")
    parser.add_argument("watermark", help="ISO-8601 UTC time; blocks edited at or after its minute")
    parser.add_argument("--source", default="notion", help="register entry to read (default: notion)")
    arguments = parser.parse_args(argv)

    try:
        source = configuration.source(arguments.source)
        locations, _ = notion_search.covered_locations(source)
        since = read_watermark(arguments.watermark)
        notion = Notion.from_source(source, notion_credential.authorization(source))

    except (configuration.ConfigurationError, notion_credential.CredentialError) as error:
        print(f"notion_page_changes: {error}", file=sys.stderr)

        return EXIT_REFUSED

    # Nothing is printed until the page is placed outside every covered location.
    try:
        page = fetch_page(notion, arguments.page_id)
        place(notion, locations, page)
        text = report(notion, page, since)

    except Refused as refusal:
        print(f"notion_page_changes: {refusal}", file=sys.stderr)

        return EXIT_REFUSED

    except Exception as error:  # noqa: BLE001 — a traceback could quote a response
        print(f"notion_page_changes: failed part-way ({type(error).__name__}); nothing printed",
              file=sys.stderr)

        return EXIT_REFUSED

    sys.stdout.write(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
