#!/usr/bin/env python3
"""Export the Notion pages under record-dense locations that changed since a watermark.

The `notion` adapter, and the **mechanical half only**, the way `chat_export.py`
is for chat. Some Notion locations carry personal records as their ordinary
content: an operations hub whose pages list individuals, a database whose rows
each describe one. Reading one through the Notion MCP server puts that content
straight into the session, and a guard that refuses the read leaves the
location unread every sync. This script is the third option. It walks each
location over Notion's REST API and writes what changed to places the session
never reads.

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

A page location is walked as a tree: the page, every block with children below
it (toggle headings, list items and columns included), each child page found
there, and each child database's rows, down to `max_depth` pages deep. Notion
does not bubble an edit up to the parent, so the whole tree is visited every
run; only the pages that changed are rendered. A database location lists every
row, so a quiet database still reports how many it checked. Its rows' own
sub-pages are walked only when the location sets `"walk_rows": true`, because
that costs a request per row.

**The watermark is inclusive at minute granularity.** Notion stamps
`last_edited_time` to the minute. A strict comparison against a seconds-precision
clock would silently skip an edit made later in the same minute as the query, so
the comparison floors the watermark to its minute and includes it. The cost is
that an edit in that minute is reported twice, which is cheap and visible. The
new watermark is the clock read before the first request (rule 1).

**A gap withholds the watermark.** Anything that means an edit could have been
missed — a location or child database that could not be read, a page that could
not be rendered, a tree deeper than `max_depth` — is named on stderr, and the run
exits 3 without printing a new watermark. The caller keeps the old one, so the
next run re-covers the window once the gap is fixed.

Exit status: 0 complete; 1 refused before any request, or failed part-way; 3
written, with gaps, watermark withheld.

Authenticates with the Notion MCP server's own token (see `notion_credential.py`),
which it never prints.
"""

import argparse
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import configuration
import notion_credential

DEFAULT_API_BASE = "https://api.notion.com/v1"
DEFAULT_MAX_DEPTH = 4
# Progress logs nest bullets deeply; Aligned's Provider Growth pages exceed 8.
# Exceeding the limit is a gap, so it is set well above what real pages reach,
# and a register can raise it further with `max_block_nesting`.
DEFAULT_MAX_BLOCK_NESTING = 24
PAGE_SIZE = 100

EXIT_REFUSED = 1
EXIT_GAPS = 3

# Notion allows an average of three requests a second per integration, and a tree
# walk issues them back to back. Pacing below that rate avoids most 429s; the
# retry honours `Retry-After` for the rest, and backs off on a transient 5xx or
# dropped connection the same way.
DEFAULT_REQUEST_INTERVAL_SECONDS = 0.35
RETRIES = 6
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# Pinned rather than taken from the MCP server's headers: the database query
# endpoint this relies on moved in later API versions, and a version chosen by
# another tool's config would change this script's behaviour underneath it.
NOTION_VERSION = "2022-06-28"

PAGE_BLOCK_TYPES = {"child_page", "child_database"}


class ExportError(Exception):
    """A request that failed. The message names the path and a status, nothing else."""


class Retryable(Exception):
    def __init__(self, description, wait_seconds):
        super().__init__(description)
        self.description = description
        self.wait_seconds = wait_seconds


class Gaps:
    """What this run could not cover. Any gap withholds the watermark."""

    def __init__(self):
        self.messages = []

    def add(self, message):
        self.messages.append(message)

    def __bool__(self):
        return bool(self.messages)


class Notion:
    """The few REST calls the export makes, over the standard library."""

    def __init__(self, api_base, authorization, request_interval=DEFAULT_REQUEST_INTERVAL_SECONDS):
        self.api_base = api_base.rstrip("/")
        self.authorization = authorization
        self.request_interval = request_interval
        self.last_request = 0.0

    def request(self, method, path, body=None):
        for attempt in range(RETRIES + 1):
            self.pace()

            try:
                return self.send(method, path, body)

            except Retryable as retryable:
                if attempt == RETRIES:
                    raise ExportError(
                        f"{method} {path} still failing after {RETRIES} retries "
                        f"({retryable.description})"
                    ) from None

                time.sleep(retryable.wait_seconds * (attempt + 1))

    def pace(self):
        wait = self.last_request + self.request_interval - time.monotonic()

        if wait > 0:
            time.sleep(wait)

        self.last_request = time.monotonic()

    def send(self, method, path, body):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.api_base}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": self.authorization,
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )

        # Every failure is reduced to a status or an exception *type*. Neither a
        # response body nor an exception's own message is ever passed on: a body
        # can quote page content, and a header error quotes the header.
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as error:
            if error.code in RETRYABLE_STATUSES:
                raise Retryable(f"status {error.code}", retry_after_seconds(error)) from None

            raise ExportError(
                f"{method} {path} returned {error.code} ({notion_error_code(error)})"
            ) from None

        except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
            raise Retryable(type(error).__name__, 1.0) from None

        except ValueError as error:
            raise ExportError(f"{method} {path} returned an unreadable body "
                              f"({type(error).__name__})") from None

    def paginated(self, method, path, body=None):
        cursor = None

        while True:
            if method == "GET":
                separator = "&" if "?" in path else "?"
                page_path = f"{path}{separator}page_size={PAGE_SIZE}"
                page_path += f"&start_cursor={cursor}" if cursor else ""
                result = self.request("GET", page_path)

            else:
                result = self.request(method, path, {**(body or {}), "page_size": PAGE_SIZE,
                                                     **({"start_cursor": cursor} if cursor else {})})

            yield from result.get("results") or []

            if not result.get("has_more"):
                return

            cursor = result.get("next_cursor")

    def page(self, page_id):
        return self.request("GET", f"/pages/{page_id}")

    def children(self, block_id):
        return list(self.paginated("GET", f"/blocks/{block_id}/children"))

    def database_rows(self, database_id):
        return list(self.paginated("POST", f"/databases/{database_id}/query", {}))


def retry_after_seconds(error):
    try:
        return max(1.0, float(error.headers.get("Retry-After") or 1))

    except (TypeError, ValueError):
        return 1.0


def notion_error_code(error):
    """Notion's own error code, never its message: a message can quote content."""
    try:
        code = json.loads(error.read().decode("utf-8")).get("code")

    except (ValueError, OSError, AttributeError):
        return "no code"

    return code if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,64}", code) else "no code"


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def floor_to_minute(moment):
    return moment.replace(second=0, microsecond=0)


def edited_since(item, since):
    return parse_time(item["last_edited_time"]) >= since


def format_time(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def changed_in_location(notion, location, since, max_depth, gaps):
    """The changed pages under one location, and how many pages were checked."""
    walk = Walk(notion, location, max_depth, gaps,
                int(location.get("max_block_nesting", DEFAULT_MAX_BLOCK_NESTING)))

    if location.get("kind") == "database":
        walk.database(location["id"], 0, walk_rows=bool(location.get("walk_rows")))

    else:
        walk.page_tree(location["id"], 0)

    changed = [page for page in walk.pages.values() if edited_since(page, since)]

    return changed, len(walk.pages)


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


def render_blocks(notion, block_id, depth=0):
    lines = []

    for block in notion.children(block_id):
        indent = "  " * depth
        rendered = render_block(block)

        if rendered:
            lines.append(indent + rendered.replace("\n", f"\n{indent}"))

        if block.get("has_children") and block["type"] not in PAGE_BLOCK_TYPES:
            if depth >= DEFAULT_MAX_BLOCK_NESTING:
                lines.append(f"{indent}*(deeper blocks not rendered)*")

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


def render_location(notion, location, since, max_depth, side_files, gaps):
    lines = [f"## {location['name']}", ""]

    try:
        changed, checked = changed_in_location(notion, location, since, max_depth, gaps)

    except ExportError as error:
        gaps.add(f"{location['name']} could not be read: {error}")

        return lines + ["**Unreadable this run**; see the gaps the adapter reported.", ""], 0, 0

    if not changed:
        return lines + [f"No page edited since the watermark ({checked} checked).", ""], checked, 0

    lines += [f"{len(changed)} page(s) edited since the watermark, of {checked} checked.", ""]

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

    return lines, checked, len(changed)


def build_export(notion, locations, since, max_depth, side_files, gaps):
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
        lines, checked, changed = render_location(notion, location, since, max_depth, side_files,
                                                  gaps)
        body += lines
        checked_total += checked
        changed_total += changed

    return "\n".join(header + body), checked_total, changed_total


def read_locations(source):
    locations = source.get("covered_locations") or []

    if not locations:
        raise configuration.ConfigurationError(
            'the source lists no "covered_locations", so there is nothing to export. A run '
            "that walks nothing would report a quiet source it never looked at."
        )

    for location in locations:
        if not isinstance(location, dict) or not location.get("id") or not location.get("name"):
            raise configuration.ConfigurationError(
                'every entry in "covered_locations" needs a "name" and an "id"'
            )

    return locations


def read_watermark(value):
    try:
        moment = parse_time(value)

    except ValueError:
        raise configuration.ConfigurationError(f"{value!r} is not an ISO-8601 time") from None

    if moment.tzinfo is None:
        raise configuration.ConfigurationError(
            f"{value!r} has no timezone; give it as UTC, e.g. {value}T00:00:00Z"
            if "T" not in value else f"{value!r} has no timezone; end it with Z"
        )

    return floor_to_minute(moment)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("watermark", help="ISO-8601 UTC time; pages edited at or after its minute")
    parser.add_argument("output", help="path to write the intake file to")
    parser.add_argument("--source", default="notion", help="register entry to read (default: notion)")
    parser.add_argument(
        "--sensitive-raw-directory",
        help="write each changed page's text here for the isolated agent",
    )
    arguments = parser.parse_args(argv)

    # Rule 1: the clock is read before the first request, and becomes the watermark.
    clock = datetime.now(timezone.utc)

    try:
        source = configuration.source(arguments.source)
        locations = read_locations(source)
        since = read_watermark(arguments.watermark)
        notion = Notion(
            source.get("api_base", DEFAULT_API_BASE),
            notion_credential.authorization(source),
            float(source.get("request_interval_seconds", DEFAULT_REQUEST_INTERVAL_SECONDS)),
        )

    except (configuration.ConfigurationError, notion_credential.CredentialError) as error:
        print(f"notion_export: {error}", file=sys.stderr)

        return EXIT_REFUSED

    if arguments.sensitive_raw_directory:
        os.makedirs(arguments.sensitive_raw_directory, exist_ok=True)

    side_files = SideFiles(arguments.sensitive_raw_directory)
    gaps = Gaps()

    # Past this point a failure is reported by type alone. An exception's message
    # can carry what it was handed — a header, a body — and a traceback prints it.
    try:
        content, checked, changed = build_export(
            notion, locations, since, int(source.get("max_depth", DEFAULT_MAX_DEPTH)),
            side_files, gaps,
        )
        Path(arguments.output).write_text(content, encoding="utf-8")

    except Exception as error:  # noqa: BLE001 — the point is that nothing escapes unreduced
        side_files.remove_all()
        print(f"notion_export: failed part-way ({type(error).__name__}); side files removed, "
              "no export written", file=sys.stderr)

        return EXIT_REFUSED

    print(arguments.output)
    print(f"{len(locations)} location(s), {checked} page(s) checked, {changed} changed")

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
