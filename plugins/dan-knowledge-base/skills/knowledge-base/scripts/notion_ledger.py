"""The lookback the Notion search adapters take for index lag, and the ledger
that keeps what the lookback finds again from being read or exported twice.

**Notion's search index is eventually consistent.** An edit can reach the index
minutes or hours after it is made, and a search run in between does not return
it. Searching from the watermark alone would then lose that edit for good: the
next run searches from a watermark already past it. So both search-based
adapters, `notion_sweep.py` and `notion_export.py` in its default mode, search
from the **lookback floor**, the watermark less the source's `index_lag_hours`
(72 by default), and still print the clock read before the first request as the
new watermark (rule 1). An edit the index shows late is found by any run whose
floor is below it.

**The ledger is what makes the overlap cheap.** The lookback still pays for a
few more search pages and placement requests, but most of what it finds again is
pages an earlier run already handled. The ledger records, by page id,
the edit time the adapter processed and the watermark of the run that processed
it, and a page found again at that same edit time is skipped entirely: not
listed, read or exported. The register names its path per source, beside the
email adapter's own:

    "ledger": "notes/.notion-ledger",
    "index_lag_hours": 72

Three rules keep a record from hiding an edit:

  * **Only a settled edit time is recorded.** Notion stamps edits to the minute,
    so a page edited again later in the clock's own minute keeps the edit time
    already read. A page edited in the run's own clock minute is not recorded;
    the next run reports it again under the minute-inclusive watermark anyway.
  * **A record counts once its run's watermark is accepted**, meaning the
    caller has passed a watermark at or after it. A run whose output was
    discarded leaves records the rerun of its window does not trust, and the
    next write drops them.
  * **It is written only by a run without gaps**, the same discipline as the
    watermark, and pruned on write to edit times at or after the lookback
    floor, since no search reaches below it.

A record also says where a page's unreported edits can begin, which is what the
sweep reads a page's blocks from (`block_window`).

The file is a JSON object keyed by page id, pretty-printed and sorted, the email
ledger's idiom, and committed like it. It holds ids and times only, never a
title, since a title can be a person's name. An unreadable ledger is read as
empty and a malformed record as absent, each with a warning: that re-reads the
overlap, which is the safe direction.

`notion_export.py --walk` searches from the watermark, not the floor, but writes
the ledger pruned against the floor all the same, so the records the next search
run skips by survive a walk.

A source naming no ledger is searched with the lookback all the same, and the
overlap is processed again every run. The adapter says so on stderr, once, so a
missing ledger shows rather than passing as quiet re-reading.
"""

import json
import sys
from datetime import timedelta
from pathlib import Path

import configuration
from notion_api import floor_to_minute, format_time, parse_time
from notion_search import normalize

DEFAULT_INDEX_LAG_HOURS = 72


def index_lag(source):
    """The source's `index_lag_hours` as a span, refused before any request when
    it is not a non-negative number."""
    hours = source.get("index_lag_hours", DEFAULT_INDEX_LAG_HOURS)

    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours < 0:
        raise configuration.ConfigurationError(
            '"index_lag_hours" must be a number of hours, zero or more'
        )

    return timedelta(hours=hours)


def read_records(path, program):
    if not path.exists():
        return {}

    try:
        records = json.loads(path.read_text(encoding="utf-8"))

    except (OSError, ValueError) as error:
        print(f"{program}: ignoring unreadable ledger at {path} ({type(error).__name__}); the "
              "lookback is processed again", file=sys.stderr)

        return {}

    if not isinstance(records, dict):
        records = {}

    well_formed_records = {page_id: record for page_id, record in records.items()
                           if well_formed(record)}

    if len(well_formed_records) < len(records):
        print(f"{program}: ignoring {len(records) - len(well_formed_records)} malformed "
              f"record(s) in the ledger at {path}; those pages are processed again",
              file=sys.stderr)

    return well_formed_records


def well_formed(record):
    """A record both of whose times are ISO-8601 strings with a timezone. Anything
    else reads as absent, which re-processes the page: the safe direction."""
    if not isinstance(record, dict):
        return False

    for field in ("last_edited_time", "watermark"):
        value = record.get(field)

        if not isinstance(value, str):
            return False

        try:
            if parse_time(value).tzinfo is None:
                return False

        except ValueError:
            return False

    return True


class Ledger:
    """The pages already processed, judged against one run's watermark (`since`)
    and lookback floor (`floor`), the edit time below which no record is kept.
    With no path it records nothing and skips nothing. The file keys each record
    by the page id as Notion gives it, so a manifest's id finds it; lookups match
    ids with or without their hyphens. `lookback` says whether this run searched
    from the floor, which a walk does not, though it prunes against it all the
    same, so that a walk keeps the records the next search needs."""

    def __init__(self, path, records, since, floor, program, lookback=True):
        self.path = path
        self.records = {normalize(page_id): (page_id, record)
                        for page_id, record in records.items()}
        self.since = since
        self.floor = floor
        self.program = program
        self.lookback = lookback and floor < since

    @classmethod
    def from_source(cls, source, source_name, since, floor, program, lookback=True):
        """The source's ledger, or an empty one that writes nowhere, said once on
        stderr when a lookback runs without one. Malformed records are dropped
        with a warning."""
        if not source.get("ledger"):
            if lookback and floor < since:
                hours = (since - floor).total_seconds() / 3600
                print(f'{program}: the source names no "ledger", so pages edited in the '
                      f"{hours:g}-hour lookback before the watermark are processed again every "
                      f'run; give it its own, e.g. "ledger": "notes/.{source_name}-ledger"',
                      file=sys.stderr)

            return cls(None, {}, since, floor, program, lookback)

        _, root = configuration.load()
        path = configuration.path_within(root, source["ledger"])

        return cls(path, read_records(path, program), since, floor, program, lookback)

    def accepted(self, identifier):
        """The page's record, by normalized id, if the run that wrote it has had
        its watermark accepted; otherwise None. Records are well formed by now."""
        _, record = self.records.get(identifier, (None, None))

        if record is None or floor_to_minute(parse_time(record["watermark"])) > self.since:
            return None

        return record

    def handled(self, item):
        """Whether the item was processed at its current edit time already."""
        record = self.accepted(normalize(item["id"]))

        return record is not None and \
            parse_time(record["last_edited_time"]) == parse_time(item["last_edited_time"])

    def block_window(self, item):
        """The earliest edit time a page's unreported edits can carry: the minute
        after the edit time last processed, or the lookback floor when that is
        older or there is no record. The record's edit time is settled, so every
        block edited at or before it was read then."""
        record = self.accepted(normalize(item["id"]))

        if record is None:
            return self.floor

        return max(self.floor,
                   floor_to_minute(parse_time(record["last_edited_time"])) + timedelta(minutes=1))

    def written(self, items, clock):
        """The records to keep: the accepted ones the lookback still reaches, and
        each item this run processed at a settled edit time."""
        settled = floor_to_minute(clock)
        kept = {identifier: entry for identifier, entry in self.records.items()
                if self.accepted(identifier) is not None
                and parse_time(entry[1]["last_edited_time"]) >= self.floor}

        for item in items:
            if parse_time(item["last_edited_time"]) < settled:
                kept[normalize(item["id"])] = (item["id"], {
                    "last_edited_time": item["last_edited_time"],
                    "watermark": format_time(clock),
                })

        return dict(kept.values())

    def write(self, items, clock):
        """Record the items this run processed. Call only on a run without gaps.
        A ledger that cannot be written is a warning, not a failure: the run's
        output stands, and the next run processes the overlap again."""
        if self.path is None:
            return

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.written(items, clock), indent=2, sort_keys=True)
                                 + "\n", encoding="utf-8")

        except OSError as error:
            print(f"{self.program}: the ledger at {self.path} could not be written "
                  f"({type(error).__name__}); the next run processes the lookback again",
                  file=sys.stderr)
