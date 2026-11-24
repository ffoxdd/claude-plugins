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
    name. It must lie under the register's intake directory, git-ignored, like
    every adapter's output (`raw_directory.output_checked`);
  * **page text**, titles and properties included, goes only to side files under
    `<intake>/<source name>/`, one per page, for a covered gate to digest. The
    run is refused before
    any request unless git ignores that folder and it is absent or empty (see
    `raw_directory.py`). With `--count-only`, pages are listed and nothing of
    theirs is written anywhere. A run that fails part-way deletes the side files
    it wrote, since no export would point at them.

The register lists the locations under the source's `covered_locations`:

    {"name": "Payments hub", "id": "<page id>"}                       a page tree
    {"name": "Practice playbooks", "id": "<db id>", "kind": "database"}

**A source that also names `open_locations` is default-deny** (see
`notion_search.py`): a page under no listed location is exported here too, in a
section of its own, with the same placeholder and side file as a covered page.
Those pages are found by the search however discovery runs, since a walk has no
location to start from for a page that is under nothing listed.

**Changed pages are found by search by default, and by a tree walk on request.**
The search asks Notion for everything edited since the lookback floor (below),
newest first, and places each result under a location by its parent chain
(`notion_search.py`). That is a few requests for the whole workspace, whatever
its size. The walk (`--walk`) visits every page under every location instead,
because Notion does not bubble an edit up to the parent: a page location is
walked as a tree, the page, every block with children below it (toggle headings,
list items and columns included), each child page found there, and each child
database's rows, down to `max_depth` pages deep, and a database location lists
every row. Its rows' own sub-pages are walked only when the location sets
`"walk_rows": true`, because that costs a request per row.

**The walk costs a request per block that has children**, not per page: finding
the child pages means listing the children of every toggle, list item and column
on the way. At the pacing in `notion_api.py` that is minutes on a large location
and up to an hour on deeply nested progress logs, and no parallelism shortens
it, since the limit is Notion's rate. So it says where it is, on stderr: a line
as each location starts, and one per page as its blocks are listed, with the
page's position, id, the `children` requests it took and the seconds. A title
can be a person's name, so no line carries one. What the walk buys is the one
case the search cannot cover, an item the index never shows at all; an edit the
index shows late is the lookback's, below. Run the walk about monthly, and
record when in the watermark note.

**The search looks back for index lag.** Notion's index is eventually
consistent, so the search starts at the watermark less the source's
`index_lag_hours` (72 by default), and a page the source's `ledger` records as
exported at its current edit time is skipped: not listed, and no side file. A
source naming no ledger exports the whole overlap again every run, and says so
on stderr. The walk takes no lookback, since it reads each page's edit time from
the page itself, with no index in between. See `notion_ledger.py`.

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
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import configuration
import file_modes
import notion_credential
import notion_search
import raw_directory
from notion_ledger import Ledger, index_lag
from notion_api import EXIT_GAPS, EXIT_REFUSED, ExportError, Gaps, Notion, edited_since, \
    format_time, read_watermark

DEFAULT_MAX_DEPTH = 4
# Progress logs nest bullets deeply; real ones exceed 8.
# Exceeding the limit is a gap, so it is set well above what real pages reach,
# and a register can raise it further with `max_block_nesting`.
DEFAULT_MAX_BLOCK_NESTING = 24

PAGE_BLOCK_TYPES = {"child_page", "child_database"}


# ---------------------------------------------------------------------------
# Discovery


class WalkProgress:
    """A line on stderr as each location starts and as each page's blocks are
    listed, so an hour-long walk does not read as a hang. Ids and numbers only:
    a title can be a person's name, and stderr reaches transcripts."""

    def __init__(self, locations):
        self.locations = locations
        self.location = 0
        self.pages = 0

    def location_started(self, location):
        self.location += 1
        self.emit(f"location {self.location}/{self.locations} {location['name']}: walking")

    def page_listed(self, page_id, requests, seconds):
        self.pages += 1
        self.emit(f"page {self.pages} {page_id}: {requests} children request(s) in {seconds:.1f} s")

    @staticmethod
    def emit(message):
        print(message, file=sys.stderr, flush=True)


class Walk:
    """One location's traversal: every page seen, and the gaps met on the way."""

    def __init__(self, notion, location, max_depth, gaps, progress,
                 max_block_nesting=DEFAULT_MAX_BLOCK_NESTING):
        self.notion = notion
        self.location = location
        self.max_depth = max_depth
        self.max_block_nesting = max_block_nesting
        self.gaps = gaps
        self.progress = progress
        self.pages = {}

    def gap(self, message):
        self.gaps.add(f"{self.location['name']}: {message}")

    def page_tree(self, page_id, depth, page=None):
        if page_id in self.pages:
            return

        started = time.monotonic()
        self.pages[page_id] = page or self.notion.page(page_id)
        blocks = self.listed_page_blocks(page_id, started)

        if depth >= self.max_depth:
            if blocks:
                self.gap(f"pages below depth {self.max_depth} were not walked; raise max_depth")

            return

        for block in blocks:
            if block["type"] == "child_page":
                try:
                    self.page_tree(block["id"], depth + 1)

                except ExportError as error:
                    self.gap(f"a child page could not be walked: {error}")

            else:
                self.database(block["id"], depth + 1, walk_rows=False)

    def listed_page_blocks(self, page_id, started):
        """The page's child pages and databases, reported as a progress line once
        listed and before the walk descends into them."""
        requests_before = self.notion.requests
        blocks = self.page_blocks(page_id)
        self.progress.page_listed(page_id, self.notion.requests - requests_before,
                                  time.monotonic() - started)

        return blocks

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
        that has children: a toggle heading, a list item, a column, a callout. A
        request for each such block, which is the walk's whole cost."""
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
    Complete, at a request per block that has children."""

    def __init__(self, notion, since, max_depth, gaps, progress):
        self.notion = notion
        self.since = since
        self.max_depth = max_depth
        self.gaps = gaps
        self.progress = progress

    def changed(self, location):
        """The changed pages, and how many pages were checked to find them."""
        self.progress.location_started(location)
        walk = Walk(self.notion, location, self.max_depth, self.gaps, self.progress,
                    int(location.get("max_block_nesting", DEFAULT_MAX_BLOCK_NESTING)))

        if location.get("kind") == "database":
            walk.database(location["id"], 0, walk_rows=bool(location.get("walk_rows")))

        else:
            walk.page_tree(location["id"], 0)

        return [page for page in walk.pages.values() if edited_since(page, self.since)], len(walk.pages)


# The section for pages under no listed location, in a register naming open
# locations. Not a location anyone walks: only the search finds its pages.
UNLISTED = {"name": "Under no listed location", "id": None}


class SearchDiscovery:
    """The changed pages under a location, as Notion's search lists them and the
    parent chain places them. One search serves every location, from the
    lookback floor rather than the watermark, so an edit the index showed late
    is still found. With `open_locations` it also serves UNLISTED."""

    def __init__(self, notion, locations, floor, gaps, open_locations=None):
        self.notion = notion
        self.locations = locations
        self.open_locations = open_locations
        self.floor = floor
        self.gaps = gaps
        self.changes = None

    def changed(self, location):
        """The changed pages, and None for the checked count: a search checks the
        workspace, not a location."""
        if self.changes is None:
            self.changes = notion_search.changes_since(self.notion, self.locations, self.floor,
                                                       self.gaps, open_locations=self.open_locations)

        if location is UNLISTED:
            found = self.changes.unlisted

        else:
            found = self.changes.under.get(location["name"], [])

        return [item for item in found if item.get("object") == "page"], None


class WithUnlisted:
    """A walk for the listed locations, and the search for UNLISTED."""

    def __init__(self, walk, search):
        self.walk = walk
        self.search = search

    def changed(self, location):
        if location is UNLISTED:
            return self.search.changed(location)

        return self.walk.changed(location)


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
        "· raw text*",
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
        self.directory = directory
        self.written = []

    def write(self, page_id, text):
        path = self.directory / f"{re.sub(r'[^A-Za-z0-9-]+', '_', page_id)}.md"
        path.write_text(text, encoding="utf-8")
        self.written.append(path)

        return path

    def remove_all(self):
        """The count of files that could not be removed."""
        if not self.directory:
            return 0

        return raw_directory.take_back(self.written, self.directory)


def placeholder(page, side_file):
    lines = [
        f"### Page `{page['id']}`, edited {page['last_edited_time']}",
        "",
        "**Record-dense location — NOT pulled verbatim.**",
    ]

    if side_file:
        lines.append(f"Raw text: `{side_file}`.")

    return lines + [""]


def checked_phrase(checked):
    return f"{checked} checked" if checked is not None else "found by search"


def render_location(notion, location, discovery, side_files, gaps, ledger):
    """The location's section, the pages it checked, and the changed pages it
    exported. A page the ledger has exported at its current edit time is not
    one of them."""
    lines = [f"## {location['name']}", ""]

    try:
        found, checked = discovery.changed(location)

    except ExportError as error:
        gaps.add(f"{location['name']} could not be read: {error}")

        return lines + ["**Unreadable this run**; see the gaps the adapter reported.", ""], 0, []

    changed = [page for page in found if not ledger.handled(page)]

    if not changed:
        return lines + [f"No changed page ({checked_phrase(checked)}).", ""], checked or 0, []

    lines += [f"{len(changed)} changed page(s) ({checked_phrase(checked)}).", ""]

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

    return lines, checked or 0, changed


def lookback_lines(ledger):
    if not ledger.lookback:
        return []

    return [f"Also pages edited since `{format_time(ledger.floor)}`, the lookback for search index",
            "lag, unless already exported at their current edit time."]


def build_export(notion, locations, discovery, side_files, gaps, ledger):
    """The export's text, the pages checked, and the changed pages exported."""
    header = [
        f"# Notion export (record-dense locations) — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"Pages edited at or after `{format_time(ledger.since)}` (the watermark, floored to",
        "Notion's minute granularity). Assembled mechanically by the knowledge-base notion",
        "adapter.",
        *lookback_lines(ledger),
        "",
    ]
    body = []
    checked_total = 0
    exported = []

    for location in locations:
        lines, checked, changed = render_location(notion, location, discovery, side_files, gaps,
                                                  ledger)
        body += lines
        checked_total += checked
        exported += changed

    return "\n".join(header + body), checked_total, exported


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("watermark", help="ISO-8601 UTC time; pages edited at or after its minute")
    parser.add_argument("output", help="path to write the intake file to, under the intake "
                                       "directory")
    parser.add_argument("--source", default="notion", help="register entry to read (default: notion)")
    parser.add_argument(
        "--count-only", action="store_true",
        help="list changed pages without writing any of their text",
    )
    parser.add_argument(
        "--walk", action="store_true",
        help="find changed pages by walking every page under each location, rather than "
             "by search; complete, at a request per block that has children, so minutes "
             "to an hour on deeply nested pages. The monthly check for an item the search "
             "index never shows",
    )
    arguments = parser.parse_args(argv)

    # Rule 1: the clock is read before the first request, and becomes the watermark.
    clock = datetime.now(timezone.utc)

    try:
        source = configuration.source(arguments.source)
        locations = notion_search.read_locations(source)
        opened = notion_search.open_locations(source)
        since = read_watermark(arguments.watermark)
        # The walk searches from the watermark, but the ledger is pruned against
        # the lookback floor either way, so a walk keeps what the next search skips.
        ledger = Ledger.from_source(source, arguments.source, since, since - index_lag(source),
                                    "notion_export", lookback=not arguments.walk)
        notion = Notion.from_source(source, notion_credential.authorization(source))
        directory = None if arguments.count_only else raw_directory.checked(arguments.source)
        output = raw_directory.output_checked(arguments.output)

    except (configuration.ConfigurationError, notion_credential.CredentialError) as error:
        print(f"notion_export: {error}", file=sys.stderr)

        return EXIT_REFUSED

    if directory:
        raw_directory.begin(directory)

    side_files = SideFiles(directory)
    gaps = Gaps()
    raw_directory.stop_on_signals()
    completed = False

    search = SearchDiscovery(notion, locations, ledger.floor, gaps, opened)
    sections = locations + ([UNLISTED] if opened is not None else [])

    if arguments.walk:
        walk = TreeWalkDiscovery(notion, since, int(source.get("max_depth", DEFAULT_MAX_DEPTH)),
                                 gaps, WalkProgress(len(locations)))
        discovery = WithUnlisted(walk, search)

    else:
        discovery = search

    # Past this point a failure is reported by type alone. An exception's message
    # can carry what it was handed — a header, a body — and a traceback prints it.
    try:
        content, checked, exported = build_export(notion, sections, discovery, side_files, gaps,
                                                  ledger)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        completed = True

    except Exception as error:  # noqa: BLE001 — the point is that nothing escapes unreduced
        print(f"notion_export: failed part-way ({type(error).__name__}); no export written",
              file=sys.stderr)

        return EXIT_REFUSED

    finally:
        if not completed and directory:
            print(f"notion_export: {raw_directory.taken_back_line(side_files.remove_all())}",
                  file=sys.stderr)

    if directory:
        raw_directory.finish(directory)

    print(output)
    changed = len(exported)

    if arguments.walk:
        print(f"{len(locations)} location(s), {checked} page(s) checked, {changed} changed")

    else:
        print(f"{len(locations)} location(s), {changed} changed, found by search")

    if not changed:
        print("Nothing to digest: skip the gate.")

    elif arguments.count_only:
        print("Changed pages were listed only; run without --count-only to have them "
              "summarized.")

    if gaps:
        print("Watermark not advanced: keep the previous one, so the next run re-covers "
              "this window.")
        print("\nGaps — each may hide an edit:", file=sys.stderr)

        for message in gaps.messages:
            print(f"  - {message}", file=sys.stderr)

        return EXIT_GAPS

    # Like the watermark, the ledger moves only when nothing could have been missed.
    ledger.write(exported, clock)
    print(f"New watermark: {format_time(clock)}")

    return 0


def utf8_streams():
    """Claude Code reads stdout and stderr as UTF-8; left to the locale, a Windows
    Python would encode them with the console code page and raise on the first
    character it lacks — a bullet, an em dash, an emoji in a page title."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    utf8_streams()
    file_modes.owner_only()
    sys.exit(main())
