#!/usr/bin/env python3
"""Print the blocks of one Notion page edited since a watermark, with their
ancestors for context and, on a page listed for them, the comments left since.

The page-changes tool. The sweep (`notion_sweep.py`) runs it on every page it
lists and writes the result to its output file; run it here by hand for one
page. Fetching a page whole through the MCP server returns every block it has
ever held, and on a page written into weekly that is a year of agendas, image
URLs included, to read one new section. This prints the new section instead:

  * a block is **printed when it was edited at or after the watermark**, in
    full, with its own edited descendants below it;
  * an unchanged ancestor is printed as **one line of context**, marked as such,
    so a new bullet still reads under its heading;
  * an unchanged block that is nobody's ancestor is not printed at all;
  * on a page the register lists for comments (below), the **comments** created
    since the watermark are printed under the block they sit on, with the
    author's name, and the page's own comments come first. Any other page says
    in one line that its comments were not read;
  * images and files are named, never linked: a signed file URL is a few
    hundred characters that say nothing.

**The walk is complete, so its cost is the page's size, not its change count.**
Notion does not move a block's edit time when a block inside it is edited, so no
branch can be skipped: every block with children is listed. A page of several
hundred blocks takes a minute or more; run it in the background rather than
cutting it short.

**Comments are read only on pages listed for them.** A comment moves no edit
time, not even its block's, so finding one means asking every walked block for
its comments, a request a block, which more than doubles the walk. Comments are
rarely where durable content lands, so that cost is paid only where the register
asks for it: a page listed under `comment_pages`, or one at or under a listed
page or database, at any depth, has every walked block asked, and the page's own
list too. Notion's page-level list leaves out most comments anchored to blocks,
so it cannot stand in for the per-block requests. Every other page makes no
comment request at all. With no `comment_pages`, comments are read nowhere:

    "comment_pages": [{"name": "Design reviews", "id": "<page id>"}]

**A newest-first page is read from the top only.** A page the register lists
under `newest_first_pages` grows by inserting each new section above the last,
so its first few top-level blocks are where any edit lands; only those are
walked, and the rest are counted, not read:

    "newest_first_pages": [{"name": "Weekly reviews", "id": "<page id>", "blocks": 2}]

Choose `blocks` to cover every section still being edited — the section being
written and the one being reviewed — since an edit below them goes unseen.

**A shallow location is read at its top level only.** The full walk exists for
nested content: Notion moves no edit time on a block when something inside it
changes, so only descending finds the change. A flat page — a CRM row of
hundreds of top-level paragraphs under a heading or two — keeps its content at
the top level, where each block's own edit time is reliable. The register lists
the location such pages sit under, a database or a parent page, and every page
at or under it, at any depth, walks only the top-level blocks edited since the
watermark, with their children as usual:

    "shallow_locations": [{"name": "CRM", "id": "<database id>"}]

Either way the whole top level is listed, which is cheap, and on a page listed
for comments the page's own comments are still asked for; an unchanged top-level
block is asked for nothing, so an edit nested under one, or a comment on one,
goes unseen. A page's own `newest_first_pages` entry beats a shallow location
above it. `comment_pages` combines with either: it decides whether comments are
asked for, and they are asked of the blocks the other rules walk. A location found
by parent chain (`notion_search.Ancestry`) whose chain cannot be followed
applies nothing: the page is read whole, which costs time but misses nothing.

The sweep's `skipped_locations` are not read here: a page asked for by hand is
read, wherever it sits.

**What it cannot read is a gap, never a silence.** A comment request that
fails, or blocks nested deeper than it walks, is reported on stderr and makes
the exit status 3, so a caller holding a watermark keeps the old one. A comment
on a page not listed for comments is not a gap: the page's report says it was
not asked for.

**One thing no poll can see:** a comment left on a page nobody edited. The
comment moves no edit time, not even the page's, so no search returns the page
and nothing runs this on it, listed or not. Only a full walk of the workspace
would find it.

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

Exit status: 0 printed; 1 refused, before any content is printed; 3 printed,
with gaps.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import configuration
import notion_credential
import notion_search
from notion_api import EXIT_GAPS, EXIT_REFUSED, ExportError, Gaps, Notion, created_since, \
    edited_since, format_time, parse_time, read_watermark
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


def block_tree(notion, block_id, since, gaps, nesting=0):
    return nodes_of(notion, notion.children(block_id), since, gaps, nesting)


def nodes_of(notion, blocks, since, gaps, nesting=0):
    nodes = []

    for block in blocks:
        children = []

        if block.get("has_children") and block["type"] not in PAGE_BLOCK_TYPES:
            if nesting < DEFAULT_MAX_BLOCK_NESTING:
                children = block_tree(notion, block["id"], since, gaps, nesting + 1)

            else:
                gaps.add(f"block {block['id']} nests deeper than {DEFAULT_MAX_BLOCK_NESTING} "
                         "levels; what is below it was not read")

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


def comments_since(notion, block_id, since, gaps):
    try:
        return [comment for comment in notion.comments(block_id) if created_since(comment, since)]

    except ExportError as error:
        gaps.add(f"comments on {block_id} could not be read ({error})")

        return []


def attach_comments(notion, nodes, since, gaps):
    """Every block is asked, changed or not: a comment does not edit its block."""
    for node in nodes:
        node.comments = comments_since(notion, node.block["id"], since, gaps)
        attach_comments(notion, node.children, since, gaps)


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


def comment_ids(nodes):
    return {comment["id"] for node in nodes for comment in node.comments} | \
        {identifier for node in nodes for identifier in comment_ids(node.children)}


def count_comments(nodes):
    return sum(len(node.comments) + count_comments(node.children) for node in nodes)


def place(notion, locations, page, ancestry=None):
    try:
        location = notion_search.Placement(notion, locations, ancestry).location_of(page)

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


class NewestFirst:
    """The first few top-level blocks of a page that grows at the top."""

    mode = "newest-first"

    def __init__(self, blocks):
        self.blocks = blocks

    def select(self, top_level, since):
        return top_level[:self.blocks]

    def note(self, walked, listed):
        return [f"*Listed as newest-first: only the first {walked} top-level block(s) were "
                f"walked; {listed - walked} older one(s) were not read.*", ""]


class Shallow:
    """The top-level blocks edited since the watermark, of a page that is flat."""

    mode = "shallow"

    def select(self, top_level, since):
        return [block for block in top_level if edited_since(block, since)]

    def note(self, walked, listed):
        return [f"*Read shallow: only top-level blocks edited since the watermark were walked "
                f"({walked} of {listed}); an edit nested under an unchanged block, or a comment "
                "on one, is not seen.*", ""]


def entries_of(source, key):
    entries = source.get(key, [])

    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise configuration.ConfigurationError(f'"{key}" must be a list of objects')

    return entries


def entry_label(entry):
    return entry.get("name", entry.get("id", "?"))


def has_id(entry):
    return isinstance(entry.get("id"), str) and bool(entry["id"])


def newest_first_blocks(source):
    """How many top-level blocks to walk, by page, for the pages the source lists
    as newest-first."""
    limits = {}

    for entry in entries_of(source, "newest_first_pages"):
        blocks = entry.get("blocks")

        if not has_id(entry) or not isinstance(blocks, int) or isinstance(blocks, bool) \
                or blocks < 1:
            raise configuration.ConfigurationError(
                f"newest_first_pages entry {entry_label(entry)!r} needs an "
                '"id" and a positive whole number of "blocks"'
            )

        limits[notion_search.normalize(entry["id"])] = blocks

    return limits


def location_names(source, key):
    """The name of each location the source lists under `key`, by its id."""
    names = {}

    for entry in entries_of(source, key):
        if not has_id(entry) or not entry.get("name"):
            raise configuration.ConfigurationError(
                f"{key} entry {entry_label(entry)!r} needs a \"name\" and an \"id\""
            )

        names[notion_search.normalize(entry["id"])] = entry["name"]

    return names


def nearest(lineage, identifiers):
    """The first id of the lineage that is one of these, or None."""
    return next((identifier for identifier in lineage if identifier in identifiers), None)


class ReadingRules:
    """How much of a page the register says to read: none of it, under a skipped
    location; part of its top level, when newest-first or under a shallow
    location; otherwise all of it. And, separately, whether its comments are
    read: only at or under a page or database listed under `comment_pages`.

    Covered locations are not among them: those are excluded before any rule is
    asked, and no rule here can bring one back."""

    def __init__(self, newest_first, shallow, skipped, commented=None):
        self.newest_first = newest_first
        self.shallow = shallow
        self.skipped = skipped
        self.commented = commented or {}

    @classmethod
    def from_source(cls, source):
        """The source's rules, refused before any request when an entry is malformed."""
        return cls(newest_first_blocks(source),
                   location_names(source, "shallow_locations"),
                   location_names(source, "skipped_locations"),
                   location_names(source, "comment_pages"))

    def reads_comments(self, page, ancestry):
        """Whether the page sits at or under a location listed for comments."""
        if not self.commented:
            return False

        return nearest(ancestry.lineage(page), self.commented) is not None

    def skipped_by(self, page, ancestry):
        """The name of the skipped location the page sits at or under, or None."""
        if not self.skipped:
            return None

        return self.skipped.get(nearest(ancestry.lineage(page), self.skipped))

    def scope_for(self, page, ancestry):
        """Which of the page's top-level blocks to walk, or None for all of them.
        Its own newest-first entry wins over a shallow location above it."""
        identifier = notion_search.normalize(page["id"])

        if identifier in self.newest_first:
            return NewestFirst(self.newest_first[identifier])

        if self.shallow and nearest(ancestry.lineage(page), self.shallow):
            return Shallow()

        return None


def count_nodes(nodes):
    return sum(1 + count_nodes(node.children) for node in nodes)


COMMENTS_NOT_READ = "Comments not read: the page is not listed under `comment_pages`."


class PageReport:
    """One page's changes, rendered, with the counts a caller reports."""

    def __init__(self, text, changed, comments, comments_read, walked):
        self.text = text
        self.changed = changed
        self.comments = comments
        self.comments_read = comments_read
        self.walked = walked


def page_comments_since(notion, page, nodes, since, gaps):
    """The page's own comments. Asked by page id, Notion can return comments
    anchored to blocks too, which are already printed under their block."""
    placed = comment_ids(nodes)

    return [comment for comment in comments_since(notion, page["id"], since, gaps)
            if comment["id"] not in placed]


def report_header(page, since, heading, comments):
    described = ("; comments left since the watermark under the blocks they sit on"
                 if comments else "")

    return [
        f"{heading} {page_title(page)} — changes since {format_time(since)}",
        "",
        f"*Page `{page['id']}`, last edited {page['last_edited_time']}. Blocks edited since the "
        f"watermark, with unchanged ancestors for context{described}.*",
        "",
    ]


def report_footer(changed, comments, comments_read):
    lines = []

    if not changed and not comments:
        left = " and no comment left" if comments_read else ""
        lines.append(f"No block edited{left} since the watermark. The page's own edit time "
                     "moved, so a property or something this does not read changed.")

    if comments_read:
        return lines + ["", f"*{changed} changed block(s), {comments} comment(s).*"]

    return lines + ["", f"*{changed} changed block(s).* {COMMENTS_NOT_READ}"]


def page_report(notion, page, since, gaps, heading="#", authors=None, scope=None,
                comments=False):
    """The page's changes. A `scope` walks only the top-level blocks it selects;
    `comments` asks every walked block, and the page, for comments, and without
    it no comment request is made."""
    top_level = notion.children(page["id"])
    walked = scope.select(top_level, since) if scope else top_level
    nodes = nodes_of(notion, walked, since, gaps)
    page_comments = []

    if comments:
        attach_comments(notion, nodes, since, gaps)
        page_comments = page_comments_since(notion, page, nodes, since, gaps)

    authors = authors or Authors(notion)
    lines = report_header(page, since, heading, comments)

    if scope:
        lines += scope.note(len(walked), len(top_level))

    lines += [render_comment(comment, authors) for comment in page_comments]
    lines += render_nodes(nodes, authors)

    changed = count_changed(nodes)
    found = len(page_comments) + count_comments(nodes)
    lines += report_footer(changed, found, comments)

    return PageReport("\n".join(lines) + "\n", changed, found, comments, count_nodes(nodes))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("page_id", help="the page, as the sweep manifest names it")
    parser.add_argument("watermark", help="ISO-8601 UTC time; blocks edited at or after its minute")
    parser.add_argument("--source", default="notion", help="register entry to read (default: notion)")
    arguments = parser.parse_args(argv)

    try:
        source = configuration.source(arguments.source)
        locations, _ = notion_search.covered_locations(source)
        rules = ReadingRules.from_source(source)
        since = read_watermark(arguments.watermark)
        notion = Notion.from_source(source, notion_credential.authorization(source))

    except (configuration.ConfigurationError, notion_credential.CredentialError) as error:
        print(f"notion_page_changes: {error}", file=sys.stderr)

        return EXIT_REFUSED

    gaps = Gaps()

    # Nothing is printed until the page is placed outside every covered location.
    try:
        page = fetch_page(notion, arguments.page_id)
        ancestry = notion_search.Ancestry(notion)
        place(notion, locations, page, ancestry)
        text = page_report(notion, page, since, gaps,
                           scope=rules.scope_for(page, ancestry),
                           comments=rules.reads_comments(page, ancestry)).text

    except Refused as refusal:
        print(f"notion_page_changes: {refusal}", file=sys.stderr)

        return EXIT_REFUSED

    except Exception as error:  # noqa: BLE001 — a traceback could quote a response
        print(f"notion_page_changes: failed part-way ({type(error).__name__}); nothing printed",
              file=sys.stderr)

        return EXIT_REFUSED

    sys.stdout.write(text)

    if gaps:
        print("Gaps — each may hide a change:", file=sys.stderr)

        for message in gaps.messages:
            print(f"  - {message}", file=sys.stderr)

        return EXIT_GAPS

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
    sys.exit(main())
