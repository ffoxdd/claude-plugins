#!/usr/bin/env python3
"""List the Notion pages and databases edited since a watermark, outside the
record-dense locations, and read what changed in each page.

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
  * every **other** result goes into the output file's manifest by id, kind,
    edit time and title;
  * every page in the manifest but those the register skips (below) is then
    **read with the page-changes walk** (`notion_page_changes.py`), and its
    changed blocks, and its new comments where the register lists the page for
    them, are written below the manifest, one section per page. The session reads this one file; it never runs the walk page by
    page. A database in the manifest is listed only: its edited rows are pages,
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
with `covered_by`, so the register lists them once:

    "notion": {"adapter": "notion-sweep", "covered_by": "notion-covered"}

A source may list its own `covered_locations` instead; one naming neither is
refused, since it would write every title in the workspace, record-dense
locations included.

**The watermark is inclusive at minute granularity**, as in `notion_export.py`,
and is the clock read before the first request. The search is sorted newest
first, and stops after the first page whose last result is older than the
watermark.

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
    stays in the manifest and is named in a skipped section, for locations whose
    pages are edited often and never yield anything. A skip is not a gap;
  * a page at or under a `comment_pages` entry has its comments read; every
    other page makes no comment request, since a comment costs a request per
    walked block to find and rarely carries anything durable.

    "shallow_locations": [{"name": "CRM", "id": "<database id>"}],
    "skipped_locations": [{"name": "Recruiting", "id": "<page id>"}],
    "comment_pages": [{"name": "Design reviews", "id": "<page id>"}]

A skip beats every other rule, and a page's own newest-first entry beats a
shallow location above it. `comment_pages` combines with either of those two,
and its comments are asked of the blocks they walk. Covered locations are excluded before any of this, so no rule
reaches one. See `notion_page_changes.py` for what each reads.

**A gap withholds the watermark.** A search page that could not be read, a
result whose chain could not be followed, a page whose blocks or comments could
not be read, or blocks nested past the walk's limit, is named on stderr, and the
run exits 3 without printing a new watermark. An unplaced result is written
nowhere, since it might sit under a covered location. A page that failed part-way
is listed in the manifest, with a section saying it was not read.

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
import notion_credential
import notion_search
from notion_api import EXIT_GAPS, EXIT_REFUSED, Gaps, Notion, format_time, parse_time, \
    read_watermark
from notion_export import page_title, plain_text
from notion_page_changes import Authors, ReadingRules, page_report


def item_title(item):
    if item.get("object") == "database":
        return plain_text(item.get("title")) or "(untitled)"

    return page_title(item)


def table_cell(text):
    return text.replace("|", "\\|").replace("\n", " ")


def build_manifest(changes, since, covered_source):
    lines = [
        f"# Notion sweep — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"Pages and databases edited at or after `{format_time(since)}` (the watermark, floored",
        "to Notion's minute granularity), outside the covered locations. Assembled",
        "mechanically by the knowledge-base notion-sweep adapter.",
        "",
        f"## Changed ({len(changes.outside)})",
        "",
    ]

    if changes.outside:
        lines += ["| Edited | Kind | Title | Id |", "|---|---|---|---|"]

        for item in sorted(changes.outside, key=lambda entry: entry["last_edited_time"], reverse=True):
            lines.append(f"| {format_time(parse_time(item['last_edited_time']))} | {item.get('object')} "
                         f"| {table_cell(item_title(item))} | `{item['id']}` |")

    else:
        lines.append("Nothing edited outside the covered locations since the watermark.")

    lines += ["", f"## Under covered locations — counted only, read by `{covered_source}`", ""]
    lines += [f"- {name}: {len(items)}" for name, items in sorted(changes.under.items())] or ["- none"]

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


def read_changes(notion, changes, since, gaps, rules, ancestry):
    """Every listed page, newest first, but those the rules skip. One page failing
    is a gap, not the end."""
    readings = Readings()
    authors = Authors(notion)
    pages = [item for item in changes.outside if item.get("object") == "page"]
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
            report = page_report(notion, page, since, gaps, heading="##", authors=authors,
                                 scope=scope, comments=comments)

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
    lines += [f"- {item_title(page)} — `{page['id']}`, under {location}"
              for page, location in readings.skipped]

    return "\n" + "\n".join(lines) + "\n"


def build_output(manifest, readings):
    output = manifest + skipped_section(readings)

    if not readings.sections:
        return output

    return output + "\n# What changed, page by page\n\n" + "\n".join(readings.sections)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("watermark", help="ISO-8601 UTC time; items edited at or after its minute")
    parser.add_argument("output", help="path to write the manifest to")
    parser.add_argument("--source", default="notion", help="register entry to read (default: notion)")
    arguments = parser.parse_args(argv)

    # Rule 1: the clock is read before the first request, and becomes the watermark.
    clock = datetime.now(timezone.utc)

    try:
        source = configuration.source(arguments.source)
        locations, covered_source = notion_search.covered_locations(source)
        rules = ReadingRules.from_source(source)
        since = read_watermark(arguments.watermark)
        notion = Notion.from_source(source, notion_credential.authorization(source))

    except (configuration.ConfigurationError, notion_credential.CredentialError) as error:
        print(f"notion_sweep: {error}", file=sys.stderr)

        return EXIT_REFUSED

    gaps = Gaps()
    ancestry = notion_search.Ancestry(notion)

    # Past this point a failure is reported by type alone, as in notion_export.py.
    try:
        changes = notion_search.changes_since(notion, locations, since, gaps, ancestry)
        readings = read_changes(notion, changes, since, gaps, rules, ancestry)
        Path(arguments.output).write_text(
            build_output(build_manifest(changes, since, covered_source), readings),
            encoding="utf-8",
        )

    except Exception as error:  # noqa: BLE001 — the point is that nothing escapes unreduced
        print(f"notion_sweep: failed part-way ({type(error).__name__}); no manifest written",
              file=sys.stderr)

        return EXIT_REFUSED

    print(arguments.output)
    print(f"{len(changes.outside)} changed outside covered locations, "
          f"{sum(len(items) for items in changes.under.values())} under covered locations, "
          f"{changes.unplaced} unplaced")
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
    sys.exit(main())
