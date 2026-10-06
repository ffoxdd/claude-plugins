#!/usr/bin/env python3
"""Export the Notion pages under record-dense locations that changed since a watermark.

The `notion` adapter, and the **mechanical half only**, the way `chat_export.py`
is for chat. Some Notion locations carry personal records as their ordinary
content: an operations hub whose pages list individuals, a database whose rows
each describe one. Reading one through the Notion MCP server puts that content
straight into the session, and a guard that refuses the read leaves the
location unread every sync. This script is the third option. It finds what
changed under each location over Notion's REST API and writes it to places the
session never reads.

Nothing sensitive reaches a session merely from running this:

  * **stdout** carries the output path, counts, and the new watermark;
  * **stderr** carries gaps: a location, a request path and a status or error
    type, never a response body or a header;
  * **the output file** carries one placeholder per changed page, naming the page
    by id and edit time only. Titles stay out, because a title can be a person's
    name;
  * **page text**, titles and properties included, goes only to side files under
    `--sensitive-raw-directory`, for the isolated agent that replaces each
    placeholder with a structural-facts-only summary. Without the flag, pages are
    listed and nothing of theirs is written anywhere. A run that fails part-way
    deletes the side files it wrote, since no export would point at them.

The register lists the locations under the source's `covered_locations`:

    {"name": "Payments hub", "id": "<page id>"}                       a page tree
    {"name": "Practice playbooks", "id": "<db id>", "kind": "database"}

**Changed pages are found by search by default, and by a tree walk on request.**
The search asks Notion for everything edited since the watermark, newest first,
and places each result under a location by its parent chain (`notion_search.py`).
That is a few requests for the whole workspace, whatever its size. The walk
(`--walk`) visits every page under every location instead, because Notion does
not bubble an edit up to the parent: a page location is walked as a tree, the
page, every block with children below it (toggle headings, list items and
columns included), each child page found there, and each child database's rows,
down to `max_depth` pages deep, and a database location lists every row. Its
rows' own sub-pages are walked only when the location sets `"walk_rows": true`,
because that costs a request per row. The walk is one request per page, so it
takes minutes on a large location, and it is complete in a way the search is
not: search covers what Notion has indexed, and an index can lag or miss an
item. Run the walk now and then as the check on the search, and record when in
the watermark note.

**The watermark is inclusive at minute granularity.** Notion stamps
`last_edited_time` to the minute. A strict comparison against a seconds-precision
clock would silently skip an edit made later in the same minute as the query, so
the comparison floors the watermark to its minute and includes it. The cost is
that an edit in that minute is reported twice, which is cheap and visible. The
new watermark is the clock read before the first request (rule 1).

**A gap withholds the watermark.** Anything that means an edit could have been
missed — a location or child database that could not be read, a page that could
not be rendered, a tree deeper than `max_depth`, a search result that could not
be placed — is named on stderr, and the run exits 3 without printing a new
watermark. The caller keeps the old one, so the next run re-covers the window
once the gap is fixed.

Exit status: 0 complete; 1 refused before any request, or failed part-way; 3
written, with gaps, watermark withheld.

Authenticates with the Notion MCP server's own token (see `notion_credential.py`),
which it never prints.
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import configuration
import notion_credential
import notion_search
from notion_api import EXIT_GAPS, EXIT_REFUSED, ExportError, Gaps, Notion, edited_since, \
    format_time, read_watermark

DEFAULT_MAX_DEPTH = 4
# Progress logs nest bullets deeply; Aligned's Provider Growth pages exceed 8.
# Exceeding the limit is a gap, so it is set well above what real pages reach,
# and a register can raise it further with `max_block_nesting`.
DEFAULT_MAX_BLOCK_NESTING = 24

PAGE_BLOCK_TYPES = {"child_page", "child_database"}


# ---------------------------------------------------------------------------
# Discovery


class Walk:
    """One location's traversal: every page seen, and the gaps met on the way."""

    def __init__(self, notion, location, max_depth, gaps, max_block_nesting=DEFAULT_MAX_BLOCK_NESTING):
        self.notion = notion
        self.location = location
        self.max_depth = max_depth
        self.max_block_nesting = max_block_nesting
        self.gaps = gaps
        self.pages = {}

    def gap(self, message):
        self.gaps.add(f"{self.location['name']}: {message}")

    def page_tree(self, page_id, depth, page=None):
        if page_id in self.pages:
            return

        self.pages[page_id] = page or self.notion.page(page_id)

        if depth >= self.max_depth:
            if self.page_blocks(page_id):
                self.gap(f"pages below depth {self.max_depth} were not walked; raise max_depth")

            return

        for block in self.page_blocks(page_id):
            if block["type"] == "child_page":
                try:
                    self.page_tree(block["id"], depth + 1)

                except ExportError as error:
                    self.gap(f"a child page could not be walked: {error}")

            else:
                self.database(block["id"], depth + 1, walk_rows=False)

    def database(self, database_id, depth, walk_rows):
        try:
            rows = self.notion.database_rows(database_id)

        except ExportError as error:
            self.gap(f"a database could not be queried: {error}")

            return

        for row in rows:
            if walk_rows:
                self.page_tree(row["id"], depth, page=row)

            else:
                self.pages.setdefault(row["id"], row)

    def page_blocks(self, block_id, nesting=0):
        """The child pages and databases under a block, through every non-page block
        that has children: a toggle heading, a list item, a column, a callout."""
        found = []

        for block in self.notion.children(block_id):
            if block["type"] in PAGE_BLOCK_TYPES:
                found.append(block)

            elif block.get("has_children"):
                if nesting >= self.max_block_nesting:
                    self.gap(f"blocks nested deeper than {self.max_block_nesting} were not "
                             "searched; raise max_block_nesting")
                    continue

                found += self.page_blocks(block["id"], nesting + 1)

        return found


class TreeWalkDiscovery:
    """The changed pages under a location, found by visiting every page under it.
    Complete, at a request per page."""

    def __init__(self, notion, since, max_depth, gaps):
        self.notion = notion
        self.since = since
        self.max_depth = max_depth
        self.gaps = gaps

    def changed(self, location):
        """The changed pages, and how many pages were checked to find them."""
        walk = Walk(self.notion, location, self.max_depth, self.gaps,
                    int(location.get("max_block_nesting", DEFAULT_MAX_BLOCK_NESTING)))

        if location.get("kind") == "database":
            walk.database(location["id"], 0, walk_rows=bool(location.get("walk_rows")))

        else:
            walk.page_tree(location["id"], 0)

        return [page for page in walk.pages.values() if edited_since(page, self.since)], len(walk.pages)


class SearchDiscovery:
    """The changed pages under a location, as Notion's search lists them and the
    parent chain places them. One search serves every location."""

    def __init__(self, notion, locations, since, gaps):
        self.notion = notion
        self.locations = locations
        self.since = since
        self.gaps = gaps
        self.changes = None

    def changed(self, location):
        """The changed pages, and None for the checked count: a search checks the
        workspace, not a location."""
        if self.changes is None:
            self.changes = notion_search.changes_since(self.notion, self.locations, self.since,
                                                       self.gaps)

        pages = [item for item in self.changes.under.get(location["name"], [])
                 if item.get("object") == "page"]

        return pages, None


# ---------------------------------------------------------------------------
# Rendering, for the side files only


def plain_text(rich_text):
    return "".join(part.get("plain_text", "") for part in rich_text or [])


def page_title(page):
    for value in (page.get("properties") or {}).values():
        if value.get("type") == "title":
            return plain_text(value.get("title")) or "(untitled)"

    return "(untitled)"


def property_text(value):
    kind = value.get("type")
    content = value.get(kind)

    if kind in ("title", "rich_text"):
        return plain_text(content)

    if kind in ("select", "status"):
        return (content or {}).get("name", "")

    if kind == "multi_select":
        return ", ".join(option.get("name", "") for option in content or [])

    if kind == "people":
        return ", ".join(person.get("name") or person.get("id", "") for person in content or [])

    if kind == "date":
        return " → ".join(filter(None, [(content or {}).get("start"), (content or {}).get("end")]))

    if kind == "relation":
        return f"{len(content or [])} related page(s)"

    if kind == "files":
        return ", ".join(item.get("name", "") for item in content or [])

    if kind in ("formula", "rollup"):
        inner = content or {}

        return str(inner.get(inner.get("type"), ""))

    if kind in ("created_by", "last_edited_by"):
        return (content or {}).get("name") or (content or {}).get("id", "")

    if kind == "unique_id":
        return f"{(content or {}).get('prefix') or ''}{(content or {}).get('number', '')}"

    return "" if content is None else str(content)


def render_properties(page):
    lines = []

    for name, value in (page.get("properties") or {}).items():
        if value.get("type") == "title":
            continue

        text = property_text(value)

        if text:
            lines.append(f"- **{name}**: {text}")

    return lines


def render_block(block):
    kind = block["type"]
    content = block.get(kind) or {}
    text = plain_text(content.get("rich_text"))

    if kind.startswith("heading_"):
        return "#" * (int(kind[-1]) + 2) + f" {text}"

    if kind == "bulleted_list_item":
        return f"- {text}"

    if kind == "numbered_list_item":
        return f"1. {text}"

    if kind == "to_do":
        return f"- [{'x' if content.get('checked') else ' '}] {text}"

    if kind == "code":
        return f"```\n{text}\n```"

    if kind == "table_row":
        return "| " + " | ".join(plain_text(cell) for cell in content.get("cells") or []) + " |"

    if kind == "child_page":
        return f"*(child page: {content.get('title', '')}, exported separately if it changed)*"

    if kind == "child_database":
        return f"*(child database: {content.get('title', '')})*"

    if kind in ("bookmark", "link_preview", "embed"):
        return content.get("url", "")

    if kind in ("image", "file", "pdf", "video"):
        return f"*({kind}: {plain_text(content.get('caption'))})*"

    if kind == "divider":
        return "---"

    return text


def indent_lines(rendered, depth):
    indent = "  " * depth

    return indent + rendered.replace("\n", f"\n{indent}")


def render_blocks(notion, block_id, depth=0):
    lines = []

    for block in notion.children(block_id):
        rendered = render_block(block)

        if rendered:
            lines.append(indent_lines(rendered, depth))

        if block.get("has_children") and block["type"] not in PAGE_BLOCK_TYPES:
            if depth >= DEFAULT_MAX_BLOCK_NESTING:
                lines.append(indent_lines("*(deeper blocks not rendered)*", depth))

            else:
                lines += render_blocks(notion, block["id"], depth + 1)

    return lines


def page_text(notion, location_name, page):
    """The whole side-file body, built before anything is written, so a failed
    fetch leaves no partial file behind."""
    lines = [
        f"# {page_title(page)}",
        "",
        f"*Location: {location_name} · page {page['id']} · edited {page['last_edited_time']} "
        "· raw text for the isolated agent*",
        "",
    ]
    lines += render_properties(page)
    lines += [""] + render_blocks(notion, page["id"])

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Assembly


class SideFiles:
    """The side files this run wrote, so a failed run can take them back."""

    def __init__(self, directory):
        self.directory = Path(directory) if directory else None
        self.written = []

    def write(self, page_id, text):
        path = self.directory / f"{re.sub(r'[^A-Za-z0-9-]+', '_', page_id)}.md"
        path.write_text(text, encoding="utf-8")
        self.written.append(path)

        return path

    def remove_all(self):
        for path in self.written:
            path.unlink(missing_ok=True)


def placeholder(page, side_file):
    lines = [
        f"### Page `{page['id']}`, edited {page['last_edited_time']}",
        "",
        "**Record-dense location — NOT pulled verbatim.** Replace this with a",
        "structural-facts-only summary: standing policy, mechanics, backlog items, defect",
        "patterns with counts, named business entities. No personal names, identifiers, or",
        "per-person amounts, and no title that is a person's name.",
    ]

    if side_file:
        lines.append(f"Raw text: `{side_file}` — local scratch, deleted once the summary is written.")

    return lines + [""]


def checked_phrase(checked):
    return f"{checked} checked" if checked is not None else "found by search"


def render_location(notion, location, discovery, side_files, gaps):
    lines = [f"## {location['name']}", ""]

    try:
        changed, checked = discovery.changed(location)

    except ExportError as error:
        gaps.add(f"{location['name']} could not be read: {error}")

        return lines + ["**Unreadable this run**; see the gaps the adapter reported.", ""], 0, 0

    if not changed:
        return (lines + [f"No page edited since the watermark ({checked_phrase(checked)}).", ""],
                checked or 0, 0)

    lines += [f"{len(changed)} page(s) edited since the watermark ({checked_phrase(checked)}).", ""]

    for page in sorted(changed, key=lambda item: item["last_edited_time"]):
        side_file = None

        if side_files.directory:
            try:
                side_file = side_files.write(page["id"], page_text(notion, location["name"], page))

            except ExportError as error:
                gaps.add(f"{location['name']}: page {page['id']} could not be rendered: {error}")
                lines += [f"### Page `{page['id']}`: **could not be rendered this run**", ""]
                continue

        lines += placeholder(page, side_file)

    return lines, checked or 0, len(changed)


def build_export(notion, locations, since, discovery, side_files, gaps):
    header = [
        f"# Notion export (record-dense locations) — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"Pages edited at or after `{format_time(since)}` (the watermark, floored to Notion's",
        "minute granularity). Assembled mechanically by the knowledge-base notion adapter;",
        "the summaries are not written yet.",
        "",
    ]
    body = []
    checked_total = 0
    changed_total = 0

    for location in locations:
        lines, checked, changed = render_location(notion, location, discovery, side_files, gaps)
        body += lines
        checked_total += checked
        changed_total += changed

    return "\n".join(header + body), checked_total, changed_total


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("watermark", help="ISO-8601 UTC time; pages edited at or after its minute")
    parser.add_argument("output", help="path to write the intake file to")
    parser.add_argument("--source", default="notion", help="register entry to read (default: notion)")
    parser.add_argument(
        "--sensitive-raw-directory",
        help="write each changed page's text here for the isolated agent",
    )
    parser.add_argument(
        "--walk", action="store_true",
        help="find changed pages by walking every page under each location, rather than "
             "by search; complete, and a request per page",
    )
    arguments = parser.parse_args(argv)

    # Rule 1: the clock is read before the first request, and becomes the watermark.
    clock = datetime.now(timezone.utc)

    try:
        source = configuration.source(arguments.source)
        locations = notion_search.read_locations(source)
        since = read_watermark(arguments.watermark)
        notion = Notion.from_source(source, notion_credential.authorization(source))

    except (configuration.ConfigurationError, notion_credential.CredentialError) as error:
        print(f"notion_export: {error}", file=sys.stderr)

        return EXIT_REFUSED

    if arguments.sensitive_raw_directory:
        os.makedirs(arguments.sensitive_raw_directory, exist_ok=True)

    side_files = SideFiles(arguments.sensitive_raw_directory)
    gaps = Gaps()

    if arguments.walk:
        discovery = TreeWalkDiscovery(notion, since, int(source.get("max_depth", DEFAULT_MAX_DEPTH)),
                                      gaps)

    else:
        discovery = SearchDiscovery(notion, locations, since, gaps)

    # Past this point a failure is reported by type alone. An exception's message
    # can carry what it was handed — a header, a body — and a traceback prints it.
    try:
        content, checked, changed = build_export(notion, locations, since, discovery, side_files,
                                                 gaps)
        Path(arguments.output).write_text(content, encoding="utf-8")

    except Exception as error:  # noqa: BLE001 — the point is that nothing escapes unreduced
        side_files.remove_all()
        print(f"notion_export: failed part-way ({type(error).__name__}); side files removed, "
              "no export written", file=sys.stderr)

        return EXIT_REFUSED

    print(arguments.output)

    if arguments.walk:
        print(f"{len(locations)} location(s), {checked} page(s) checked, {changed} changed")

    else:
        print(f"{len(locations)} location(s), {changed} changed, found by search")

    if not changed:
        print("Nothing to summarize: skip the isolated agent.")

    elif not arguments.sensitive_raw_directory:
        print("Changed pages were listed only; pass --sensitive-raw-directory to have them "
              "summarized.")

    if gaps:
        print("Watermark not advanced: keep the previous one, so the next run re-covers "
              "this window.")
        print("\nGaps — each may hide an edit:", file=sys.stderr)

        for message in gaps.messages:
            print(f"  - {message}", file=sys.stderr)

        return EXIT_GAPS

    print(f"New watermark: {format_time(clock)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
