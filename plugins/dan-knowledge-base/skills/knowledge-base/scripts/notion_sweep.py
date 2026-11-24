#!/usr/bin/env python3
"""List the Notion pages and databases edited since a watermark, outside the
record-dense locations, and read what changed in each readable page.

The `notion-sweep` adapter: the workspace-wide half of a Notion sync, run as a
script so no model pages through search results or block trees. A sweep done
through the MCP server shares one result stream with the record-dense locations,
so a guard that withholds those results also stalls the pagination that runs
through them, and every retry after a refusal reads as a workaround. Here the
search runs over Notion's REST API, and each result is placed in the page tree
(`notion_search.py`) before anything of it is written:

  * a result **under a covered location** is counted against that location and
    written nowhere else. The `notion` adapter (`notion_export.py`) is the route
    that reads those, so this one never has to;
  * when the register names `open_locations`, a result **under no listed
    location** is handled the same way: named by id in the manifest, never read,
    and exported by the `notion` adapter;
  * a result whose parent chain **cannot be followed** is named by id in the
    manifest, never read, and is a gap;
  * every **readable** result — under an open location, or, without
    `open_locations`, outside every covered location — goes into the output
    file's manifest by id, kind, edit time and title. The output file must lie
    under the register's intake directory, git-ignored, like every adapter's
    output (`raw_directory.output_checked`);
  * every page in the manifest but those the register skips (below) is then
    **read with the page-changes walk** (`notion_page_changes.py`), and its
    changed blocks, and its new comments where the register lists the page for
    them, are written below the manifest, one section per page. The file is
    raw intake like every adapter's output: a batch for a covered gate where one
    exists, read directly by the session a register requires, and read as any
    intake otherwise. Nobody runs the walk page by page. A database in the manifest is listed only: its edited rows are pages,
    and arrive as their own results;
  * **stdout** carries the output path, counts and the new watermark, and
    **stderr** carries progress, gaps, a request path and a status only. Neither
    carries a title.

**Progress goes to stderr, a line as each page starts and one as it ends**, so a
long walk does not read as a hang: the page's position in the run, its id and
how it is read (`full`, `shallow`, `newest-first` or `skipped`, plus `comments`
when listed for them), then the blocks it walked and the seconds it took. A
title can be a person's name, so no progress line carries one.

The covered locations are the `covered_locations` of the source this one names
with `covered_by`, and its `open_locations` beside them, so the register lists
them once (`notion_search.py`):

    "notion": {"adapter": "notion-sweep", "covered_by": "notion-covered"}

A source may list its own `covered_locations` and `open_locations` instead; one
naming neither is refused, since it would write every title in the workspace,
record-dense locations included.

**The watermark is inclusive at minute granularity**, as in `notion_export.py`,
and is the clock read before the first request. The search is sorted newest
first, and stops after the first page whose last result is older than the
lookback floor.

**The search looks back for index lag.** Notion's index is eventually
consistent, so the search starts at the watermark less the source's
`index_lag_hours` (72 by default), and an item the source's `ledger` records as
processed at its current edit time is dropped: not listed, not read. A source
naming no ledger processes the whole overlap again every run, and says so on
stderr. Results under a covered location are counted from the watermark only:
the covered adapter takes its own lookback. See `notion_ledger.py`.

**Each page's blocks are read from the earliest moment an edit to it could have
gone unreported**, not from the watermark. The page-changes walk prints the
blocks whose own edit time is at or after the time it is given, and a block's
edit time is not subject to the index's lag; only the page's appearance in the
search is. So a page whose edit the index showed late, read from the watermark,
would print nothing of that edit, and the same holds for a page edited once
late-indexed and again after the watermark, whose edit time then hides the
first. The time a page is read from is the minute after the edit time the ledger
last recorded for it, or the lookback floor when the record is older or absent.
Everything at or before a recorded edit time was read when it was recorded;
everything after it, up to the lookback, may not have been. With
`index_lag_hours` at 0 that is the watermark, as without a lookback.

**It reads everything, so it takes as long as the pages are long.** The walk
cannot skip a branch (see `notion_page_changes.py`), so a sync whose changed
pages hold a few thousand blocks takes several minutes. There is no time limit
to cut it short. Run it in the background. The register shapes it four ways,
each resolved by the same parent-chain walk as the covered placement, which
fetches no ancestor twice:

  * a page listed under `newest_first_pages` is read from the top only, for a
    long page that grows by inserting new sections above the old;
  * a page at or under a `shallow_locations` entry, at any depth, walks only
    the top-level blocks edited since the watermark, for flat pages — a CRM
    database whose rows are hundreds of top-level paragraphs. Notion moves no
    edit time on a parent for a nested change, which is why the full walk
    descends; a flat page has nothing nested, so its top-level times suffice;
  * a page at or under a `skipped_locations` entry is **not read at all**: it
    stays in the manifest and is named by id in a skipped section, for locations
    whose pages are edited often and never yield anything. A skip is not a gap;
  * a page at or under a `comment_pages` entry has its comments read; every
    other page makes no comment request, since a comment costs a request per
    walked block to find and rarely carries anything durable.

    "shallow_locations": [{"name": "CRM", "id": "<database id>"}],
    "skipped_locations": [{"name": "Recruiting", "id": "<page id>"}],
    "comment_pages": [{"name": "Design reviews", "id": "<page id>"}]

A skip beats every other rule, and a page's own newest-first entry beats a
shallow location above it. `comment_pages` combines with either of those two,
and its comments are asked of the blocks they walk. Only readable pages are
shaped by any of this, so no rule reaches a covered page, an unlisted one, or an
unplaced one. See `notion_page_changes.py` for what each reads.

**A gap withholds the watermark.** A search page that could not be read, a
result whose chain could not be followed, a page whose blocks or comments could
not be read, or blocks nested past the walk's limit, is named on stderr, and the
run exits 3 without printing a new watermark. An unplaced result is named by id
and nothing more, since it might sit under a covered location. A page that failed
part-way is listed in the manifest, with a section saying it was not read.

Exit status: 0 complete; 1 refused before any request, or failed part-way; 3
written, with gaps, watermark withheld.
"""

import argparse
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
from notion_api import EXIT_GAPS, EXIT_REFUSED, Gaps, Notion, edited_since, format_time, \
    parse_time, read_watermark
from notion_export import page_title, plain_text
from notion_ledger import Ledger, index_lag
from notion_page_changes import Authors, ReadingRules, page_report


def item_title(item):
    if item.get("object") == "database":
        return plain_text(item.get("title")) or "(untitled)"

    return page_title(item)


def table_cell(text):
    return text.replace("|", "\\|").replace("\n", " ")


def unprocessed(changes, ledger):
    """The search's changes, less every readable item the ledger has processed at
    its current edit time. Items under a covered location, or under none, are kept
    only from the watermark: they are counted, never read, and the lookback serves
    the reads."""
    kept = notion_search.Changes(changes.default_deny)
    kept.unplaced = changes.unplaced
    kept.readable = [item for item in changes.readable if not ledger.handled(item)]
    kept.unlisted = [item for item in changes.unlisted if edited_since(item, ledger.since)]
    kept.under = {location: [item for item in items if edited_since(item, ledger.since)]
                  for location, items in changes.under.items()}
    kept.under = {location: items for location, items in kept.under.items() if items}

    return kept


def lookback_lines(ledger):
    if not ledger.lookback:
        return []

    return [f"Also items edited since `{format_time(ledger.floor)}`, the lookback for search index",
            "lag, unless already processed at their current edit time."]


def readable_scope(changes):
    if changes.default_deny:
        return "under the open locations"

    return "outside the covered locations"


def identified(heading, items):
    """A section naming items by id only: a title can be a person's name."""
    if not items:
        return []

    return ["", f"{heading} ({len(items)})", ""] + [f"- `{item['id']}`" for item in items]


def build_manifest(changes, ledger, covered_source):
    scope = readable_scope(changes)
    lines = [
        f"# Notion sweep — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"Pages and databases edited at or after `{format_time(ledger.since)}` (the watermark,",
        f"floored to Notion's minute granularity), {scope}. Assembled",
        "mechanically by the knowledge-base notion-sweep adapter.",
        *lookback_lines(ledger),
        "",
        f"## Changed ({len(changes.readable)})",
        "",
    ]

    if changes.readable:
        lines += ["| Edited | Kind | Title | Id |", "|---|---|---|---|"]

        for item in sorted(changes.readable, key=lambda entry: entry["last_edited_time"], reverse=True):
            lines.append(f"| {format_time(parse_time(item['last_edited_time']))} | {item.get('object')} "
                         f"| {table_cell(item_title(item))} | `{item['id']}` |")

    else:
        lines.append(f"Nothing edited {scope} since the watermark.")

    lines += ["", f"## Under covered locations — counted only, read by `{covered_source}`", ""]
    lines += [f"- {name}: {len(items)}" for name, items in sorted(changes.under.items())] or ["- none"]
    lines += identified(f"## Under no open location — not read, exported by `{covered_source}`",
                        changes.unlisted)
    lines += identified("## Unplaced — not read; each is a gap", changes.unplaced)

    return "\n".join(lines) + "\n"


class Readings:
    """The changes read from every listed page, the pages skipped, and their totals."""

    def __init__(self):
        self.sections = []
        self.skipped = []
        self.pages = 0
        self.changed = 0
        self.comments = 0
        self.commented = 0


class Progress:
    """A line on stderr as each page starts and ends. Ids, modes and numbers
    only: a title can be a person's name, and stderr reaches transcripts."""

    def __init__(self, total):
        self.total = total
        self.position = 0
        self.page_id = None
        self.started = None

    def next(self, page):
        """Count the page, before anything about it is asked."""
        self.position += 1
        self.page_id = page["id"]
        self.started = None

    def start(self, mode):
        self.started = time.monotonic()
        self.emit(mode)

    def finish(self, outcome):
        """The page's closing line, if its opening one was printed."""
        if self.started is not None:
            self.emit(f"{outcome} in {time.monotonic() - self.started:.1f} s")

    def emit(self, message):
        print(f"page {self.position}/{self.total} {self.page_id}: {message}", file=sys.stderr,
              flush=True)


def reading_mode(scope, comments):
    mode = scope.mode if scope else "full"

    return f"{mode}, comments" if comments else mode


def read_changes(notion, changes, ledger, gaps, rules, ancestry):
    """Every listed page, newest first, but those the rules skip, each read from
    its own block window (see the module docstring). One page failing is a gap,
    not the end."""
    readings = Readings()
    authors = Authors(notion)
    pages = [item for item in changes.readable if item.get("object") == "page"]
    progress = Progress(len(pages))

    for page in sorted(pages, key=lambda entry: entry["last_edited_time"], reverse=True):
        progress.next(page)

        try:
            location = rules.skipped_by(page, ancestry)

            if location is not None:
                progress.emit("skipped")
                readings.skipped.append((page, location))
                continue

            scope = rules.scope_for(page, ancestry)
            comments = rules.reads_comments(page, ancestry)
            progress.start(reading_mode(scope, comments))
            report = page_report(notion, page, ledger.block_window(page), gaps, heading="##",
                                 authors=authors, scope=scope, comments=comments)

        except Exception as error:  # noqa: BLE001 — reduced to a type, as everywhere here
            gaps.add(f"page {page['id']} could not be read ({type(error).__name__})")
            readings.sections.append(f"## {item_title(page)} — not read\n\n"
                                     f"Page `{page['id']}` failed part-way; the next run "
                                     "re-reads it.\n")

            progress.finish(f"failed ({type(error).__name__})")
            continue

        progress.finish(f"{report.walked} block(s) walked")
        readings.sections.append(report.text)
        readings.pages += 1
        readings.changed += report.changed
        readings.comments += report.comments
        readings.commented += 1 if report.comments_read else 0

    return readings


def skipped_section(readings):
    if not readings.skipped:
        return ""

    lines = [f"## Skipped — listed, not read ({len(readings.skipped)})", "",
             "Under a location the register lists as `skipped_locations`.", ""]
    lines += [f"- `{page['id']}`, under {location}" for page, location in readings.skipped]

    return "\n" + "\n".join(lines) + "\n"


def build_output(manifest, readings):
    output = manifest + skipped_section(readings)

    if not readings.sections:
        return output

    return output + "\n# What changed, page by page\n\n" + "\n".join(readings.sections)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("watermark", help="ISO-8601 UTC time; items edited at or after its minute")
    parser.add_argument("output", help="path to write the manifest to, under the intake "
                                       "directory")
    parser.add_argument("--source", default="notion", help="register entry to read (default: notion)")
    arguments = parser.parse_args(argv)

    # Rule 1: the clock is read before the first request, and becomes the watermark.
    clock = datetime.now(timezone.utc)

    try:
        source = configuration.source(arguments.source)
        listing = notion_search.listed_locations(source)
        rules = ReadingRules.from_source(source)
        since = read_watermark(arguments.watermark)
        ledger = Ledger.from_source(source, arguments.source, since, since - index_lag(source),
                                    "notion_sweep")
        notion = Notion.from_source(source, notion_credential.authorization(source))
        output = raw_directory.output_checked(arguments.output)

    except (configuration.ConfigurationError, notion_credential.CredentialError) as error:
        print(f"notion_sweep: {error}", file=sys.stderr)

        return EXIT_REFUSED

    gaps = Gaps()
    ancestry = notion_search.Ancestry(notion)

    # Past this point a failure is reported by type alone, as in notion_export.py.
    try:
        changes = unprocessed(
            notion_search.changes_since(notion, listing.covered, ledger.floor, gaps, ancestry,
                                        listing.open), ledger)
        readings = read_changes(notion, changes, ledger, gaps, rules, ancestry)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            build_output(build_manifest(changes, ledger, listing.reader), readings),
            encoding="utf-8",
        )

    except Exception as error:  # noqa: BLE001 — the point is that nothing escapes unreduced
        print(f"notion_sweep: failed part-way ({type(error).__name__}); no manifest written",
              file=sys.stderr)

        return EXIT_REFUSED

    print(output)
    print(f"{len(changes.readable)} changed {readable_scope(changes)}, "
          f"{sum(len(items) for items in changes.under.values())} under covered locations, "
          f"{unlisted_count(changes)}{len(changes.unplaced)} unplaced")
    print(f"{readings.pages} page(s) read: {readings.changed} changed block(s); comments read "
          f"on {readings.commented} page(s) listed under comment_pages, "
          f"{readings.comments} new; {len(readings.skipped)} skipped")

    if gaps:
        print("Watermark not advanced: keep the previous one, so the next run re-covers "
              "this window.")
        print("\nGaps — each may hide an edit:", file=sys.stderr)

        for message in gaps.messages:
            print(f"  - {message}", file=sys.stderr)

        return EXIT_GAPS

    # Like the watermark, the ledger moves only when nothing could have been missed.
    # Every item listed was processed: read, skipped by rule, or, for a database,
    # listed only.
    ledger.write(changes.readable, clock)
    print(f"New watermark: {format_time(clock)}")

    return 0


def unlisted_count(changes):
    if not changes.default_deny:
        return ""

    return f"{len(changes.unlisted)} under no open location, "


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
