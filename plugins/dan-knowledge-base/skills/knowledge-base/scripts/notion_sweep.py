#!/usr/bin/env python3
"""List the Notion pages and databases edited since a watermark, outside the
record-dense locations.

The `notion-sweep` adapter: the workspace-wide "what changed?" half of a Notion
sync, run as a script so no model pages through search results. A sweep done
through the MCP server shares one result stream with the record-dense locations,
so a guard that withholds those results also stalls the pagination that runs
through them, and every retry after a refusal reads as a workaround. Here the
search runs over Notion's REST API, and each result is placed in the page tree
before anything of it is written:

  * a result **under a covered location** is counted against that location and
    written nowhere else. The `notion` adapter (`notion_export.py`) is the route
    that reads those, so this one never has to;
  * every **other** result goes into the output file by id, kind, edit time and
    title, for the session to choose from and fetch through the MCP server;
  * **stdout** carries the output path, counts and the new watermark, and
    **stderr** carries gaps, a request path and a status only. Neither carries a
    title.

The covered locations are the `covered_locations` of the source this one names
with `covered_by`, so the register lists them once:

    "notion": {"adapter": "notion-sweep", "covered_by": "notion-covered"}

A source may list its own `covered_locations` instead; one naming neither is
refused, since it would write every title in the workspace, record-dense
locations included.

**Placement walks the parent chain**, one metadata request per ancestor not yet
seen, cached for the run. A chain that reaches the workspace, or an ancestor the
integration cannot see, is outside every covered location: a covered location is
shared with the integration, and sharing reaches everything beneath it, so a
chain leading into one is visible all the way up to it.

**The watermark is inclusive at minute granularity**, as in `notion_export.py`,
and is the clock read before the first request. The search is sorted newest
first, and stops after the first page whose last result is older than the
watermark.

**A gap withholds the watermark.** A search page that could not be read, or a
result whose chain could not be followed, is named on stderr, and the run exits
3 without printing a new watermark. An unplaced result is written nowhere, since
it might sit under a covered location.

Exit status: 0 complete; 1 refused before any request, or failed part-way; 3
written, with gaps, watermark withheld.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import configuration
import notion_credential
from notion_export import (
    DEFAULT_API_BASE,
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    EXIT_GAPS,
    EXIT_REFUSED,
    PAGE_SIZE,
    ExportError,
    Gaps,
    Notion,
    edited_since,
    format_time,
    page_title,
    parse_time,
    plain_text,
    read_locations,
    read_watermark,
)

# Deeper than any real workspace nests; a chain this long is a cycle or a defect.
MAX_ANCESTRY = 64

# The parent types that name another item, and the call that fetches each.
PARENT_KINDS = ("page_id", "database_id", "block_id")


class Unplaceable(Exception):
    """A result whose parent chain could not be followed."""


def normalize(identifier):
    return identifier.replace("-", "").lower()


class Placement:
    """Which covered location, if any, each item sits under, cached per run."""

    def __init__(self, notion, locations):
        self.notion = notion
        self.locations = {normalize(location["id"]): location["name"] for location in locations}
        self.known = {}

    def location_of(self, item):
        """The covered location's name, or None when the item is outside all of them."""
        chain = []
        current = item

        for _ in range(MAX_ANCESTRY):
            identifier = normalize(current["id"])

            if identifier in self.known:
                return self.settle(chain, self.known[identifier])

            chain.append(identifier)

            if identifier in self.locations:
                return self.settle(chain, self.locations[identifier])

            parent = current.get("parent") or {}

            if parent.get("type") not in PARENT_KINDS:
                return self.settle(chain, None)

            try:
                current = self.fetch(parent["type"], parent[parent["type"]])

            except ExportError as error:
                if error.status == 404:
                    return self.settle(chain, None)

                raise Unplaceable(str(error)) from None

        raise Unplaceable(f"a parent chain longer than {MAX_ANCESTRY} items")

    def fetch(self, kind, identifier):
        if kind == "page_id":
            return self.notion.page(identifier)

        if kind == "database_id":
            return self.notion.database(identifier)

        return self.notion.block(identifier)

    def settle(self, chain, location):
        for identifier in chain:
            self.known[identifier] = location

        return location


def search_since(notion, since, gaps):
    """Every search result edited at or after the watermark, newest first."""
    body = {"sort": {"direction": "descending", "timestamp": "last_edited_time"},
            "page_size": PAGE_SIZE}

    while True:
        try:
            result = notion.request("POST", "/search", body)

        except ExportError as error:
            gaps.add(f"a search page could not be read: {error}")

            return

        items = result.get("results") or []
        yield from (item for item in items if edited_since(item, since))

        if not result.get("has_more") or not items or not edited_since(items[-1], since):
            return

        body = {**body, "start_cursor": result.get("next_cursor")}


def item_title(item):
    if item.get("object") == "database":
        return plain_text(item.get("title")) or "(untitled)"

    return page_title(item)


def table_cell(text):
    return text.replace("|", "\\|").replace("\n", " ")


class Sweep:
    def __init__(self):
        self.changed = []
        self.covered = {}
        self.unplaced = 0

    def add(self, item, location):
        if location is None:
            self.changed.append(item)

        else:
            self.covered[location] = self.covered.get(location, 0) + 1


def run_sweep(notion, locations, since, gaps):
    placement = Placement(notion, locations)
    sweep = Sweep()

    for item in search_since(notion, since, gaps):
        try:
            sweep.add(item, placement.location_of(item))

        except Unplaceable as error:
            sweep.unplaced += 1
            gaps.add(f"item {item['id']} could not be placed: {error}")

    return sweep


def build_manifest(sweep, since, covered_source):
    lines = [
        f"# Notion sweep — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"Pages and databases edited at or after `{format_time(since)}` (the watermark, floored",
        "to Notion's minute granularity), outside the covered locations. Assembled",
        "mechanically by the knowledge-base notion-sweep adapter.",
        "",
        f"## Changed ({len(sweep.changed)})",
        "",
    ]

    if sweep.changed:
        lines += ["| Edited | Kind | Title | Id |", "|---|---|---|---|"]

        for item in sorted(sweep.changed, key=lambda entry: entry["last_edited_time"], reverse=True):
            lines.append(f"| {format_time(parse_time(item['last_edited_time']))} | {item.get('object')} "
                         f"| {table_cell(item_title(item))} | `{item['id']}` |")

    else:
        lines.append("Nothing edited outside the covered locations since the watermark.")

    lines += ["", f"## Under covered locations — counted only, read by `{covered_source}`", ""]
    lines += [f"- {name}: {count}" for name, count in sorted(sweep.covered.items())] or ["- none"]

    return "\n".join(lines) + "\n"


def covered_locations(source):
    """The locations to exclude, and the source whose adapter reads them."""
    if "covered_by" in source:
        name = source["covered_by"]

        return read_locations(configuration.source(name)), name

    if "covered_locations" in source:
        return source["covered_locations"], "the notion adapter"

    raise configuration.ConfigurationError(
        'the source names no "covered_by" source and lists no "covered_locations". A '
        "sweep with nothing to exclude writes every title in the workspace, record-dense "
        'locations included; list them, or give "covered_locations": [] to mean none.'
    )


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
        locations, covered_source = covered_locations(source)
        since = read_watermark(arguments.watermark)
        notion = Notion(
            source.get("api_base", DEFAULT_API_BASE),
            notion_credential.authorization(source),
            float(source.get("request_interval_seconds", DEFAULT_REQUEST_INTERVAL_SECONDS)),
        )

    except (configuration.ConfigurationError, notion_credential.CredentialError) as error:
        print(f"notion_sweep: {error}", file=sys.stderr)

        return EXIT_REFUSED

    gaps = Gaps()

    # Past this point a failure is reported by type alone, as in notion_export.py.
    try:
        sweep = run_sweep(notion, locations, since, gaps)
        Path(arguments.output).write_text(build_manifest(sweep, since, covered_source),
                                          encoding="utf-8")

    except Exception as error:  # noqa: BLE001 — the point is that nothing escapes unreduced
        print(f"notion_sweep: failed part-way ({type(error).__name__}); no manifest written",
              file=sys.stderr)

        return EXIT_REFUSED

    print(arguments.output)
    print(f"{len(sweep.changed)} changed outside covered locations, "
          f"{sum(sweep.covered.values())} under covered locations, {sweep.unplaced} unplaced")

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
