#!/usr/bin/env python3
"""List the Notion pages and databases edited since a watermark, outside the
record-dense locations.

The `notion-sweep` adapter: the workspace-wide "what changed?" half of a Notion
sync, run as a script so no model pages through search results. A sweep done
through the MCP server shares one result stream with the record-dense locations,
so a guard that withholds those results also stalls the pagination that runs
through them, and every retry after a refusal reads as a workaround. Here the
search runs over Notion's REST API, and each result is placed in the page tree
(`notion_search.py`) before anything of it is written:

  * a result **under a covered location** is counted against that location and
    written nowhere else. The `notion` adapter (`notion_export.py`) is the route
    that reads those, so this one never has to;
  * every **other** result goes into the output file by id, kind, edit time and
    title, for the session to choose from and fetch with the page-changes tool
    (`notion_page_changes.py`) or through the MCP server;
  * **stdout** carries the output path, counts and the new watermark, and
    **stderr** carries gaps, a request path and a status only. Neither carries a
    title.

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
import notion_search
from notion_api import EXIT_GAPS, EXIT_REFUSED, Gaps, Notion, format_time, parse_time, \
    read_watermark
from notion_export import page_title, plain_text


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
        since = read_watermark(arguments.watermark)
        notion = Notion.from_source(source, notion_credential.authorization(source))

    except (configuration.ConfigurationError, notion_credential.CredentialError) as error:
        print(f"notion_sweep: {error}", file=sys.stderr)

        return EXIT_REFUSED

    gaps = Gaps()

    # Past this point a failure is reported by type alone, as in notion_export.py.
    try:
        changes = notion_search.changes_since(notion, locations, since, gaps)
        Path(arguments.output).write_text(build_manifest(changes, since, covered_source),
                                          encoding="utf-8")

    except Exception as error:  # noqa: BLE001 — the point is that nothing escapes unreduced
        print(f"notion_sweep: failed part-way ({type(error).__name__}); no manifest written",
              file=sys.stderr)

        return EXIT_REFUSED

    print(arguments.output)
    print(f"{len(changes.outside)} changed outside covered locations, "
          f"{sum(len(items) for items in changes.under.values())} under covered locations, "
          f"{changes.unplaced} unplaced")

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
