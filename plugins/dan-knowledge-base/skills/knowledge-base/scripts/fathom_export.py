#!/usr/bin/env python3
"""Export the Fathom meetings created since a watermark: recap and transcript.

The `fathom` adapter, and the **mechanical half only**, the way
`notion_export.py` is for record-dense Notion locations. A meeting is held for
its attendees, and a meeting with a customer can name that customer's members or
patients in passing: the decision worth keeping sits next to the case that
prompted it. So each meeting is fetched over Fathom's public API and written to a
raw file under the intake directory, one meeting per file, which is one batch for
a covered gate to digest. Fetching costs no model tokens at all.

**The transcript is passed verbatim, with the recap beside it.** Measured on 15
meetings (2026-11), Fathom's recap carries about 56% of a transcript's
substantive facts, and a model-written compaction of the transcript misattributes
speakers, reverses who asks whom and firms up hedges several times a meeting. So
whatever reads the meeting, the gate or the session, reads every word of it.

Nothing sensitive reaches a session merely from running this:

  * **stdout** carries the output path, counts, the recording ids of meetings
    whose summary is not ready yet or whose transcript is unavailable, and the
    new watermark. Never a title, a name, an address or a word of a meeting;
  * **stderr** carries gaps: a request path and a status or error type, never a
    response body or a header;
  * **the output file** carries one placeholder per exported meeting, naming it
    by recording id and recorded date and pointing at its meeting file. Titles
    stay out, because a title can be a person's name. It must lie under the
    register's intake directory, git-ignored, like every adapter's output
    (`raw_directory.output_checked`);
  * **the meeting itself** goes only to its meeting file under
    `<intake>/<source name>/`: the title, invitee domains (never addresses),
    `## Summary`, `## Action items` and, when the source asks for transcripts,
    `## Transcript`. With `--count-only`, meetings
    are listed and counted, nothing of theirs is written, and neither the ledger
    nor the watermark advances. A run that fails part-way, or is interrupted
    or terminated, deletes the meeting files it wrote, since no export would
    point at them.

**The meeting files live in the repository, git-ignored**, where a gate's
isolated run reaches them however its tools are scoped.
The folder is the register's intake folder joined with `--source`, and the run is
refused before any request unless git ignores it and it is absent or empty (see
`raw_directory.py`).

The register entry:

    "meetings": {
      "adapter": "fathom",
      "watermark": {"format": "iso-8601", "boundary": "exclusive"},
      "ledger": "notes/.fathom-ledger",
      "lookback_hours": 72,
      "max_lookback_days": 90,
      "excluded_invitee_domains": ["client.example"],
      "transcripts": true,
      "credential": {"key_file": "~/.config/fathom/api-key"}
    }

**A meeting with an excluded invitee is never written anywhere.** Some client
contracts forbid AI use of their meetings. A meeting any of whose calendar
invitees has an address at one of `excluded_invitee_domains`, or at a subdomain
of one, compared case-insensitively, is counted and dropped before anything of
it is written or its transcript requested. The key is required, so a forgotten
clause is a refusal rather than an export; `[]` says there is none.

**Transcripts are requested when `transcripts` is true** (false by default;
anything but a boolean is a configuration error), one request per meeting the
run exports. A turn is one speaker's consecutive lines merged, written as
`Name: text`, with turns separated by a blank line; a missing name is
`Unknown`, and timestamps and speaker addresses are not written. The words are
Fathom's, unaltered. A transcript that comes back empty, or a 404, is
**unavailable**: the meeting is exported with `Transcript unavailable.` under
its heading, counted, and named by recording id on stdout. Any other failure
that outlasts the retries is a gap that takes the export back: the meeting
files the run wrote are removed, no export is written, and the run exits 3.

**The query looks back, because a summary finishes after its meeting is
created.** Meetings are listed from the watermark less `lookback_hours` (72 by
default), and the `ledger` keeps what the overlap finds again from being
exported twice. A meeting whose summary is missing or empty is **not ready**: it
is counted, named by recording id on stdout, and left out of the ledger, so any
run whose lookback still reaches it exports it once Fathom has written it. One
still not ready past the lookback is lost, which the not-ready line is there to
make visible.

**The ledger** is a JSON object keyed by recording id, pretty-printed, sorted
and committed, like the Notion ledger. A recording id carries no personal data.
Each record holds the meeting's creation time and the watermark of the run that
exported it, and counts only once the caller has passed a watermark at or after
that one, so a run whose output was discarded leaves records its rerun ignores.
It is written only by a run without gaps that wrote meeting files, and pruned to
meetings the lookback still reaches.

**A far-back watermark is refused**, as the email adapter refuses one: a window
older than `max_lookback_days` (90 by default) lists everything in it at
Fathom's heavy-request rate. Narrow the watermark and record the gap, or pass
`--allow-backfill`.

**Requests are paced** below Fathom's limit for requests that include a
summary, 30 a minute, which Fathom says it may lower under load; transcript
requests share the same pacing. A 429 or a transient 5xx is retried after the
`Retry-After` it sends. The new watermark is the clock read before the first
request (rule 1).

**A gap withholds the watermark.** A listing page that could not be read, a
meeting with no recording id, or a transcript that could not be read is named on
stderr, and the run exits 3 without printing a new watermark or writing the
ledger.

Exit status: 0 complete; 1 refused before any request, or failed part-way; 3
gaps, watermark withheld.

Authenticates with a Fathom API key (see `fathom_credential.py`), which it never
prints.
"""

import argparse
import http.client
import json
import re
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import configuration
import fathom_credential
import file_modes
import raw_directory
from notion_api import EXIT_GAPS, EXIT_REFUSED, RETRIES, RETRYABLE_STATUSES, ExportError, Gaps, \
    Retryable, floor_to_minute, format_time, parse_time, read_watermark, retry_after_seconds

DEFAULT_API_BASE = "https://api.fathom.ai/external/v1"
DEFAULT_LOOKBACK_HOURS = 72
DEFAULT_MAX_LOOKBACK_DAYS = 90

# Thirty requests a minute is Fathom's allowance for a listing that includes
# summaries. Pacing just under it avoids most 429s; the retry honours
# `Retry-After` for the rest, including the lower limit Fathom applies under load.
DEFAULT_REQUEST_INTERVAL_SECONDS = 2.1

TRANSCRIPT_UNAVAILABLE = "Transcript unavailable."


# ---------------------------------------------------------------------------
# The API


class Fathom:
    """The listing and the transcripts the adapter reads, over the standard library."""

    def __init__(self, api_base, api_key, request_interval=DEFAULT_REQUEST_INTERVAL_SECONDS,
                 retry_wait=None):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.request_interval = request_interval
        self.retry_wait = retry_wait
        self.last_request = 0.0

    @classmethod
    def from_source(cls, source, api_key):
        retry_wait = source.get("retry_wait_seconds")

        return cls(
            source.get("api_base", DEFAULT_API_BASE),
            api_key,
            float(source.get("request_interval_seconds", DEFAULT_REQUEST_INTERVAL_SECONDS)),
            None if retry_wait is None else float(retry_wait),
        )

    def meetings_created_after(self, floor):
        """Every meeting created after `floor`, with its summary and action items,
        page by page along Fathom's cursor."""
        cursor = None

        while True:
            page = self.request("/meetings", self.listing_query(floor, cursor))
            yield from page.get("items") or []
            cursor = page.get("next_cursor")

            if not cursor:
                return

    @staticmethod
    def listing_query(floor, cursor):
        query = {
            "created_after": format_time(floor),
            "include_summary": "true",
            "include_action_items": "true",
        }

        if cursor:
            query["cursor"] = cursor

        return query

    def transcript(self, identifier):
        """A recording's transcript lines, as Fathom serves them."""
        path = f"/recordings/{urllib.parse.quote(identifier, safe='')}/transcript"

        return self.request(path, {}).get("transcript") or []

    def request(self, path, query):
        for attempt in range(RETRIES + 1):
            self.pace()

            try:
                return self.send(path, query)

            except Retryable as retryable:
                if attempt == RETRIES:
                    raise ExportError(f"GET {path} still failing after {RETRIES} retries "
                                      f"({retryable.description})") from None

                time.sleep(self.wait_seconds(retryable) * (attempt + 1))

    def wait_seconds(self, retryable):
        """The wait before a retry: what the server asked for, unless the source
        names a fixed one."""
        return retryable.wait_seconds if self.retry_wait is None else self.retry_wait

    def pace(self):
        wait = self.last_request + self.request_interval - time.monotonic()

        if wait > 0:
            time.sleep(wait)

        self.last_request = time.monotonic()

    def send(self, path, query):
        address = f"{self.api_base}{path}"

        if query:
            address += f"?{urllib.parse.urlencode(query)}"

        request = urllib.request.Request(
            address,
            method="GET",
            headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
        )

        # Every failure is reduced to a status or an exception *type*: a body can
        # quote a summary, and a header error quotes the header.
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as error:
            if error.code in RETRYABLE_STATUSES:
                raise Retryable(f"status {error.code}", retry_after_seconds(error)) from None

            raise ExportError(f"GET {path} returned {error.code}", status=error.code) from None

        except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
            raise Retryable(type(error).__name__, 1.0) from None

        except ValueError as error:
            raise ExportError(f"GET {path} returned an unreadable body "
                              f"({type(error).__name__})") from None


# ---------------------------------------------------------------------------
# The register


def hours_setting(source, key, default):
    value = source.get(key, default)

    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise configuration.ConfigurationError(f'"{key}" must be a number, zero or more')

    return value


def excluded_domains(source):
    """The excluded invitee domains, lowercased. Required, so that a contract nobody
    wrote down is a refusal rather than an export."""
    domains = source.get("excluded_invitee_domains")

    if not isinstance(domains, list) or not all(isinstance(item, str) for item in domains):
        raise configuration.ConfigurationError(
            'the source must list "excluded_invitee_domains": the domains whose meetings may '
            "not be used by AI, or [] to say there are none"
        )

    return {domain.strip().lower().lstrip("@") for domain in domains if domain.strip()}


def transcripts_setting(source):
    value = source.get("transcripts", False)

    if not isinstance(value, bool):
        raise configuration.ConfigurationError('"transcripts" must be true or false')

    return value


def lookback_refusal(since, max_lookback_days, allowed):
    """Why a run from this watermark will not go ahead, or None when it will."""
    age = datetime.now(timezone.utc) - since

    if allowed or age.days <= max_lookback_days:
        return None

    return (f"the watermark is {age.days} days back, past the register's max_lookback_days of "
            f"{max_lookback_days:g}. Advance it to a deliberate start and record the skipped gap "
            "in the sync notes, or pass --allow-backfill to export the whole window on purpose.")


# ---------------------------------------------------------------------------
# Sorting the meetings


def invitee_domains(meeting):
    domains = set()

    for invitee in meeting.get("calendar_invitees") or []:
        email = (invitee.get("email") or "").strip().lower()

        if "@" in email:
            domains.add(email.rsplit("@", 1)[1])

        if invitee.get("email_domain"):
            domains.add(invitee["email_domain"].strip().lower())

    return domains


def within(domain, excluded):
    return domain == excluded or domain.endswith(f".{excluded}")


def has_excluded_invitee(meeting, excluded):
    return any(within(domain, rule) for domain in invitee_domains(meeting) for rule in excluded)


def summary_text(meeting):
    return ((meeting.get("default_summary") or {}).get("markdown_formatted") or "").strip()


def recording_id(meeting):
    identifier = meeting.get("recording_id")

    return str(identifier) if isinstance(identifier, (int, str)) and str(identifier) else None


def recorded_date(meeting):
    for field in ("recording_start_time", "scheduled_start_time", "created_at"):
        if meeting.get(field):
            try:
                return format_time(parse_time(meeting[field]))[:10]

            except ValueError:
                continue

    return "date unknown"


class Sorting:
    """Every listed meeting, sorted into what the run does with it."""

    def __init__(self):
        self.listed = 0
        self.excluded = 0
        self.already_exported = 0
        self.not_ready = []
        self.ready = []
        self.seen = set()

    def sort(self, meetings, excluded, ledger, gaps):
        for meeting in meetings:
            identifier = recording_id(meeting)

            # A meeting can move between cursor pages while they are read.
            if identifier is not None and identifier in self.seen:
                continue

            self.listed += 1
            self.seen.add(identifier)

            if has_excluded_invitee(meeting, excluded):
                self.excluded += 1

            elif identifier is None:
                gaps.add("a listed meeting carries no recording id")

            elif ledger.handled(identifier):
                self.already_exported += 1

            elif not summary_text(meeting):
                self.not_ready.append(identifier)

            else:
                self.ready.append(meeting)


# ---------------------------------------------------------------------------
# The ledger


def well_formed(record):
    if not isinstance(record, dict):
        return False

    for field in ("created_at", "watermark"):
        try:
            if not isinstance(record.get(field), str) or parse_time(record[field]).tzinfo is None:
                return False

        except ValueError:
            return False

    return True


class Ledger:
    """The recording ids already exported, judged against one run's watermark
    (`since`) and lookback floor (`floor`). With no path it records nothing and
    skips nothing."""

    def __init__(self, path, records, since, floor):
        self.path = path
        self.records = records
        self.since = since
        self.floor = floor

    @classmethod
    def from_source(cls, source, source_name, since, floor):
        if not source.get("ledger"):
            if floor < since:
                print(f'fathom_export: the source names no "ledger", so meetings in the lookback '
                      f'are exported again every run; give it one, e.g. "ledger": '
                      f'"notes/.{source_name}-ledger"', file=sys.stderr)

            return cls(None, {}, since, floor)

        _, root = configuration.load()
        path = configuration.path_within(root, source["ledger"])

        return cls(path, read_records(path), since, floor)

    def accepted(self, identifier):
        record = self.records.get(identifier)

        if record is None or floor_to_minute(parse_time(record["watermark"])) > self.since:
            return None

        return record

    def handled(self, identifier):
        return self.accepted(identifier) is not None

    def written(self, meetings, clock):
        kept = {identifier: record for identifier, record in self.records.items()
                if self.accepted(identifier) is not None
                and parse_time(record["created_at"]) >= self.floor}

        for meeting in meetings:
            kept[recording_id(meeting)] = {
                "created_at": meeting.get("created_at") or format_time(clock),
                "watermark": format_time(clock),
            }

        return kept

    def write(self, meetings, clock):
        """Record the meetings this run exported. Call only on a run without gaps
        whose meeting files were written."""
        if self.path is None:
            return

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.written(meetings, clock), indent=2,
                                            sort_keys=True) + "\n", encoding="utf-8")

        except OSError as error:
            print(f"fathom_export: the ledger at {self.path} could not be written "
                  f"({type(error).__name__}); the next run exports the lookback again",
                  file=sys.stderr)


def read_records(path):
    if not path.exists():
        return {}

    try:
        records = json.loads(path.read_text(encoding="utf-8"))

    except (OSError, ValueError) as error:
        print(f"fathom_export: ignoring unreadable ledger at {path} ({type(error).__name__}); "
              "the lookback is exported again", file=sys.stderr)

        return {}

    if not isinstance(records, dict):
        return {}

    kept = {identifier: record for identifier, record in records.items() if well_formed(record)}

    if len(kept) < len(records):
        print(f"fathom_export: ignoring {len(records) - len(kept)} malformed record(s) in the "
              f"ledger at {path}; those meetings are exported again", file=sys.stderr)

    return kept


# ---------------------------------------------------------------------------
# Transcripts


class TranscriptGap(Exception):
    """A transcript request that failed for a reason other than its absence. The
    message names the path and a status, nothing else."""


def speaker_name(line):
    return ((line.get("speaker") or {}).get("display_name") or "").strip() or "Unknown"


def speaker_turns(lines):
    """(speaker, text) per turn: one speaker's consecutive lines merged."""
    turns = []

    for line in lines:
        text = (line.get("text") or "").strip()

        if not text:
            continue

        speaker = speaker_name(line)

        if turns and turns[-1][0] == speaker:
            turns[-1] = (speaker, f"{turns[-1][1]} {text}")

        else:
            turns.append((speaker, text))

    return turns


def rendered_transcript(lines):
    """The transcript as `Name: text` turns separated by blank lines, or None when
    it holds no words."""
    turns = speaker_turns(lines)

    if not turns:
        return None

    return "\n\n".join(f"{speaker}: {text}" for speaker, text in turns)


class Transcripts:
    """The transcripts this run fetched, and the meetings that had none."""

    def __init__(self, fathom, requested):
        self.fathom = fathom
        self.requested = requested
        self.fetched = 0
        self.unavailable = []

    def section(self, meeting):
        """The meeting file's transcript section, or no lines when the source does
        not ask for transcripts."""
        if not self.requested:
            return []

        return ["", "## Transcript", "", self.rendered(recording_id(meeting))]

    def rendered(self, identifier):
        try:
            text = rendered_transcript(self.fathom.transcript(identifier))

        except ExportError as error:
            if error.status != 404:
                raise TranscriptGap(str(error)) from None

            text = None

        if text is None:
            self.unavailable.append(identifier)

            return TRANSCRIPT_UNAVAILABLE

        self.fetched += 1

        return text


# ---------------------------------------------------------------------------
# The meeting files, the only place a meeting's content is written


def action_item_line(item):
    assignee = ((item.get("assignee") or {}).get("name") or "").strip()
    owner = f" ({assignee})" if assignee else ""
    done = "x" if item.get("completed") else " "

    return f"- [{done}] {(item.get('description') or '').strip()}{owner}"


def meeting_text(meeting, transcript_section):
    lines = [
        f"# {meeting.get('title') or meeting.get('meeting_title') or '(untitled)'}",
        "",
        f"*Recording {recording_id(meeting)} · recorded {recorded_date(meeting)} · raw text*",
        "",
        f"Invitee domains: {', '.join(sorted(invitee_domains(meeting))) or 'none listed'}",
        "",
        "## Summary",
        "",
        summary_text(meeting),
        "",
        "## Action items",
        "",
    ]
    items = meeting.get("action_items") or []
    lines += [action_item_line(item) for item in items] or ["None listed."]
    lines += transcript_section

    return "\n".join(lines) + "\n"


class MeetingFiles:
    """The meeting files this run wrote, so a failed run can take them back."""

    def __init__(self, directory, transcripts):
        self.directory = directory
        self.transcripts = transcripts
        self.written = []

    def write(self, meeting):
        name = re.sub(r"[^A-Za-z0-9-]+", "_", recording_id(meeting))
        path = self.directory / f"fathom-{name}.md"
        text = meeting_text(meeting, self.transcripts.section(meeting))

        # Recorded before the write, so a write that fails part-way is still
        # taken back; and an unencodable character is replaced rather than
        # failing every run that reaches this meeting.
        self.written.append(path)
        path.write_text(text, encoding="utf-8", errors="replace")

        return path

    def remove_all(self):
        for path in self.written:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# The export


def placeholder(meeting, meeting_file):
    lines = [f"### Meeting `{recording_id(meeting)}`, recorded {recorded_date(meeting)}", ""]

    if not meeting_file:
        return lines + ["Listed only: no meeting file was written.", ""]

    return lines + [f"Meeting file: `{meeting_file}`.", ""]


def build_export(sorting, floor, lookback_hours, meeting_files):
    lines = [
        f"# Fathom export — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"Meetings created after `{format_time(floor)}`, the watermark less a {lookback_hours:g}-hour",
        "lookback for summaries that finish late, less those already exported. Assembled",
        "mechanically by the knowledge-base fathom adapter.",
        "",
    ]

    if not sorting.ready:
        lines += ["No meeting to export.", ""]

    for meeting in sorted(sorting.ready, key=lambda item: item.get("created_at") or ""):
        meeting_file = meeting_files.write(meeting) if meeting_files.directory else None
        lines += placeholder(meeting, meeting_file)

    return "\n".join(lines)


def counts_line(sorting, exporting):
    verb = "exported" if exporting else "listed only"

    return (f"{sorting.listed} meeting(s) listed: {len(sorting.ready)} {verb}, "
            f"{sorting.excluded} skipped by invitee domain, {len(sorting.not_ready)} summary not "
            f"ready, {sorting.already_exported} already in the ledger")


def report_transcripts(transcripts, exporting):
    if not (transcripts.requested and exporting):
        return

    print(f"Transcripts: {transcripts.fetched} fetched, {len(transcripts.unavailable)} "
          "unavailable")

    if transcripts.unavailable:
        print(f"Transcript unavailable, meeting exported without it: "
              f"{', '.join(transcripts.unavailable)}")


def report_gaps(gaps):
    print("Watermark not advanced: keep the previous one, so the next run re-covers this "
          "window.")
    print("\nGaps — each may hide a meeting:", file=sys.stderr)

    for message in gaps.messages:
        print(f"  - {message}", file=sys.stderr)

    return EXIT_GAPS


def report(arguments, sorting, transcripts, gaps, ledger, clock, lookback_hours):
    exporting = not arguments.count_only
    print(arguments.output)
    print(counts_line(sorting, exporting))
    report_transcripts(transcripts, exporting)

    if sorting.not_ready:
        print(f"Summary not ready, retried by each run within the {lookback_hours:g}-hour "
              f"lookback: {', '.join(sorting.not_ready)}")

    if not sorting.ready:
        print("Nothing to digest: skip the gate.")

    if gaps:
        return report_gaps(gaps)

    if not exporting:
        print("Meetings were listed only, and the ledger and watermark were not advanced: run "
              "without --count-only to export them.")

        return 0

    ledger.write(sorting.ready, clock)
    print(f"New watermark: {format_time(clock)}")

    return 0


def read_settings(arguments):
    """Everything the run needs before its first request, or a refusal."""
    source = configuration.source(arguments.source)
    since = read_watermark(arguments.watermark)
    lookback_hours = hours_setting(source, "lookback_hours", DEFAULT_LOOKBACK_HOURS)
    floor = since - timedelta(hours=lookback_hours)
    excluded = excluded_domains(source)
    refusal = lookback_refusal(since, hours_setting(source, "max_lookback_days",
                                                    DEFAULT_MAX_LOOKBACK_DAYS),
                               arguments.allow_backfill)

    if refusal:
        raise configuration.ConfigurationError(refusal)

    requested = transcripts_setting(source)
    directory = None if arguments.count_only else raw_directory.checked(arguments.source)
    output = raw_directory.output_checked(arguments.output)
    ledger = Ledger.from_source(source, arguments.source, since, floor)
    fathom = Fathom.from_source(source, fathom_credential.api_key(source))

    return (fathom, ledger, floor, excluded, lookback_hours, Transcripts(fathom, requested),
            directory, output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("watermark", help="ISO-8601 UTC time; meetings created after it")
    parser.add_argument("output", help="path to write the intake file to, under the intake "
                                       "directory")
    parser.add_argument("--source", default="fathom", help="register entry to read (default: fathom)")
    parser.add_argument("--count-only", action="store_true",
                        help="list and count meetings without writing any meeting file; the "
                             "ledger and watermark do not advance")
    parser.add_argument("--allow-backfill", action="store_true",
                        help="export a window older than the register's max_lookback_days, "
                             "deliberately")
    arguments = parser.parse_args(argv)

    # Rule 1: the clock is read before the first request, and becomes the watermark.
    clock = datetime.now(timezone.utc)

    try:
        fathom, ledger, floor, excluded, lookback_hours, transcripts, directory, output = \
            read_settings(arguments)

    except (configuration.ConfigurationError, fathom_credential.CredentialError) as error:
        print(f"fathom_export: {error}", file=sys.stderr)

        return EXIT_REFUSED

    if directory:
        directory.mkdir(parents=True, exist_ok=True)

    meeting_files = MeetingFiles(directory, transcripts)
    gaps = Gaps()
    sorting = Sorting()
    signal.signal(signal.SIGTERM, terminate)
    completed = False

    # Past this point a failure is reported by type alone. An exception's message
    # can carry what it was handed — a header, a body — and a traceback prints it.
    # Any exit before the export is written, an interruption included, takes back
    # the meeting files, since no export would point at them.
    try:
        write_export(output, fathom, sorting, excluded, ledger, gaps, floor, lookback_hours,
                     meeting_files)
        completed = True

    except TranscriptGap as error:
        gaps.add(f"a transcript could not be read: {error}")
        print("No export written: a transcript could not be read, and the meeting files this "
              "run wrote were removed.")

        return report_gaps(gaps)

    except Exception as error:  # noqa: BLE001 — the point is that nothing escapes unreduced
        print(f"fathom_export: failed part-way ({type(error).__name__}); meeting files "
              "removed, no export written", file=sys.stderr)

        return EXIT_REFUSED

    finally:
        if not completed:
            meeting_files.remove_all()

    return report(arguments, sorting, transcripts, gaps, ledger, clock, lookback_hours)


def write_export(output, fathom, sorting, excluded, ledger, gaps, floor, lookback_hours,
                 meeting_files):
    try:
        sorting.sort(fathom.meetings_created_after(floor), excluded, ledger, gaps)

    except ExportError as error:
        gaps.add(f"the meeting listing stopped part-way: {error}")

    content = build_export(sorting, floor, lookback_hours, meeting_files)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def terminate(signal_number, frame):
    """A termination, such as a tool's time limit, unwinds like an interruption, so
    the cleanup runs."""
    raise SystemExit(128 + signal_number)


def utf8_streams():
    """Claude Code reads stdout and stderr as UTF-8; left to the locale, a Windows
    Python would encode them with the console code page and raise on the first
    character it lacks."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    utf8_streams()
    file_modes.owner_only()
    sys.exit(main())
