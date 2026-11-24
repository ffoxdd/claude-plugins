---
name: knowledge-base
description: Working in a knowledge-base repo — one that distills live sources (meeting recaps, task trackers, wikis, chat, git history) into committed notes. Carries the intake lifecycle, watermark discipline, the note types that decide how each file gets updated, and the sync procedure. Use when asked to sync, refresh, or integrate intake; when writing into such a repo; or when setting one up.
---

# The knowledge-base pattern

A git repo in two halves: **raw intake, never committed**, and **distilled
notes, committed**. Nearly everything below follows from that split.

The payoff is organizational knowledge that is greppable and reviewable: "what
do we know about X" is one `grep` over local files, how the answer changed is
in `git log`, and a claim traces to the source and date that produced it.

**This skill does not know your sources.** Which systems feed a knowledge base,
how each is queried, and the traps each hides belong in the repo's own
`CLAUDE.md`, as a register of sources, beside `.knowledge-base.json` for the
values scripts read. `references/adding-a-source.md` is how to interrogate a
new source before trusting it; `references/configuring-sources.md` is the
contract between the two files. Everything in this file is the part that is the
same everywhere.

If the repo doesn't exist yet, `/dan-knowledge-base:init` scaffolds one.

## Layout

```
inbox/             raw intake — gitignored
inbox/digests/     what a covered gate wrote from raw intake — gitignored
inbox/processed/   intake already distilled — gitignored
notes/             distilled knowledge — committed
notes/.sync-state  per-source watermarks — committed
```

**Intake is flat; the filename carries the organization:**
`YYYYMMDD_description.ext`, with a source prefix where the source isn't obvious
(`20260716_chat_billing-thread.txt`). Per-source subdirectories fragment the
unprocessed queue, which is the one thing you need to see whole.

**The unprocessed queue is a set difference** — in `inbox/`, not in
`inbox/processed/`. Moving a file after distilling it is what marks it done;
there is no status field to drift.

**A subdirectory of `inbox/` other than `processed/` is working space, not
intake.** An adapter writes raw text to `<intake>/<source>/`, one file per
batch: the intake directory the register's `layout` names, joined with the
source's name, as in `inbox/chat/`, `inbox/notion-covered/` or `inbox/fathom/`.
A covered gate writes each batch's digest to `<intake>/digests/<source>/<batch>.md`.
Both are git-ignored with the rest of the intake tree and inside the
repository, so a gate reaches them however its tools are scoped. An adapter
refuses to run, before any request, when its folder is in a work tree git does
not ignore, when git cannot judge it, or when it already holds files: those are
a previous run's, so finish its digests or move them to processed. These files
never join the queue; they move to `inbox/processed/` once integrated.

**Raw intake is never committed.** It is an order of magnitude larger than what
it yields, it rots, and it is the material most likely to carry what must never
enter a repo — personal data, a pasted credential, a third party's numbers.
Gitignoring the whole intake tree is what makes pulling *anything* in safe,
because the pull stops being a publication decision.

**Everything an adapter fetches lands under the intake directory, and nowhere
else.** An adapter refuses an output path outside it, or one git does not
ignore, and creates what it writes readable by its owner alone. Where a covered
gate is in force the session reads only the digests it releases (below), so
never choose an output path outside intake to get around that.

**`layout.retention_days`**, when the register sets it, deletes processed intake
older than that many days at session start, and reports the count in one line.
It deletes nothing unless the processed directory is inside the intake
directory, git-ignored, and reached through no symbolic link.

## Self-authored capture is an input, not a section

A journal, daily log, or other raw personal capture is a **source** like
anything from outside, and lives outside `notes/`: a grep for what the
organization knows should not read half-thoughts and todos. When an entry turns
out to be durable, **promote** it into the note that owns the subject rather
than copying it. Whether to keep such capture at all is a personal practice this
pattern has no opinion about.

## Note types decide how a note is updated

Every note in `notes/` is an **accumulator by default** — enriched in place,
never replaced wholesale. Two other kinds declare themselves in the note's own
frontmatter: `note-type: snapshot` (rewritten whole each sync, describing only
what is true now) and `note-type: log` (append-only, newest first, entries never
revised). Check the frontmatter of the note in front of you; there is no central
list to maintain. Full semantics, the snapshot/log pair, and the queue pattern
for expensive output documents: `references/note-types.md`.

## Watermark discipline

Four rules, each preventing a silent failure.

1. **Read the clock before you query, and make that reading the next
   watermark** — not the newest returned item's timestamp. Compact projections
   often omit timestamps, and an item modified between clock and query is then
   re-reported next sync (cheap, visible) instead of skipped (neither). The
   exception the shipped adapters take: a source that stamps every item with a
   reliable time and returns them in order lets the high-water-mark of processed
   items be the watermark — tighter and deterministic, and safer against a
   late-indexed item than the clock, which would advance past it.

2. **Establish whether the source's boundary is inclusive.** Many APIs treat a
   watermark as `>=` and re-deliver the boundary item on every sync forever.
   Filter with a strict `>` yourself. The exception is a source whose timestamps
   are coarser than the clock: Notion stamps edits to the minute, so a strict `>`
   against a seconds-precision watermark loses an edit made in the query's own
   minute. There, floor the watermark to the source's granularity and compare
   inclusively, accepting a duplicate in exchange for never missing an edit.

3. **Advance the watermark even when nothing changed, and write down why.** A
   quiet source and a broken query look identical in a file of timestamps.
   "Nothing above the prior watermark; asserted by re-running with an older one,
   which returned the known items" is evidence; a bare timestamp is not.

4. **A source deliberately skipped gets a note too**, so the next sync can tell
   a decision from an omission.

## The sync procedure

A request starts a sync — "sync the knowledge base", "pull in what's new",
"integrate the inbox" — and this skill is the whole workflow it runs. Asked how
to run one, say the phrase and what it does: distills the new material into
notes, advances the watermarks, commits, and leaves the push.

1. **Read the repo's source register** (its `CLAUDE.md`) for which sources
   exist, how each is queried, and each watermark's format.
2. **List the unprocessed queue** — in `inbox/`, not in `inbox/processed/`.
3. **Read `notes/.sync-state`.** Anything older than roughly a day is worth
   syncing.
4. **Record the wall clock now, per source, before querying it** (rule 1).
5. **Sweep for what changed, cheaply** — `references/sweep-economics.md`. Then
   fetch in full only the items the sweep says are substantive.
6. **Distill each item into the right note(s)**, per each note's type: insert a
   dated entry at the top of a log without reading the rest; rewrite a snapshot
   whole, deleting what the new information retires; add to or correct the
   relevant section of an accumulator.
7. **Move each processed intake file to `inbox/processed/`.**
8. **Write the new watermarks**, with a per-source note — including the
   no-change and the skipped ones.
9. **Commit without asking. Push only when asked.** A sync is routine and its
   whole output is a reviewable diff, so a wrong commit costs an amend, while a
   confirmation prompt on every sync costs more than the mistakes it prevents.
   Pushing is what makes a mistake expensive to undo, so that stays a request.

## Notes name no individual whose case they record

A note records what the organization knows, not about whom: aggregates, counts,
mechanics, and people in their business roles. No note carries the name of, an
identifier for, or the particulars of one person's case — dates finer than the
year, an age, family make-up, life events — for anyone whose own situation is
the subject. A described case is identifying without a name, so write the
pattern ("two members whose dependents were missing"), never the case.

## Provenance is per-fact, and not optional

When a fact enters a note, record where it came from and when — the person and
date who confirmed it, or the source and its date. Without it a note degrades
into undated assertions nobody can re-check or age out, and the first
contradiction between two is unresolvable.

Provenance is attribution, not chronology. A snapshot carries the first and must
not accumulate the second; `references/note-types.md` covers why.

## Navigation is the directory tree, not cross-links

Organize notes into folders with filenames clear enough to browse. No
hand-written index and no dense web of inter-note links: both rot silently, and
both turn moving one note into edits across many. Cross-link only for a
genuinely non-obvious relationship, at most once per note per target.

## Searching notes/

One case-insensitive multi-pattern call rather than one per term:

```
grep -rn -i -e pattern-one -e pattern-two notes/
```

**A search returning nothing is not evidence the topic is absent.** Company,
product, and person names are routinely misspelled by whatever captured them —
a transcription pass renders an unfamiliar name phonetically. Try the spellings
speech-to-text would produce before concluding the knowledge base lacks it.

## Sources that mix durable content with personal records

Some sources carry both in one body: an operations log with standing policy
between per-person rows, a support channel where the useful pattern is
surrounded by the cases that revealed it. Reading one directly pulls those
records into the session for content that was only ever going to be committed
as aggregates.

**A register may require a session variable** (`session.required_variable`).
Then the whole sync — adapters, reading raw intake, distilling, committing —
happens in the session that sets it, which reads raw intake directly because it
is itself the covered side; the gate procedure below does not apply. In any
other session the adapters refuse and session start says so: stop and say that
the sync must run there, rather than look for another route. What such a session
writes into notes is what leaves the covered side, so the rule above on
individuals is the boundary.

**A covered gate exists where your organization's covered-endpoint plugin is
installed**, and its own instructions say so in the session. Without one, the
session reads raw intake directly and distils it like any other. With one, raw
intake never crosses the gate:

1. **A script does the mechanical half** — fetch, dedupe, group — writing raw
   text under the intake directory, one file per batch, and printing ids and
   counts only. The session runs it itself.
2. **The session never opens a raw intake file.** For each batch it hands the
   gate the raw file paths, the digest path, and `references/digest-brief.md`,
   the knowledge-base half of the gate's brief (with
   `references/transcripts.md` for a meeting). The gate's own instructions carry
   what a digest must leave out, and state the size of batch it accepts.
3. **A batch is one conversation, one meeting, or one group of pages** where it
   fits within the gate's limits; a larger one is split.
4. **The session reads a digest only once the gate releases it.** A digest the
   gate refuses is produced again by a fresh gate run from the raw files; the
   session never edits a digest toward release.
5. **Readers read digests only**, the session and any sub-agent alike. A reader
   that meets content about an individual in a digest stops reading it, carries
   nothing from it, and reports it, by filename, as an exposure. Nothing else
   depends on this tripwire; it exists to catch what the gate let through.
6. **Once a digest is integrated into notes**, its raw files, the digest and the
   run's export move to `inbox/processed/`, where retention deletes them.

`references/chat-sources.md` covers chat, the hardest instance.

## Running the shipped adapters

Five adapters ship in the `scripts/` directory **beside this file**. Invoke them
by absolute path built from the directory this skill was loaded from — written
below as `<SKILL_DIR>`. Never hardcode or remember that path: it carries a
version that changes on every plugin update.

An adapter reads the register itself, from the working directory, so the only
arguments are the watermark and where to write, a path under the intake
directory. The chat, Notion and Fathom adapters also write raw text to the
source's folder there (see Layout); `--count-only` writes none, and says what
that leaves undone.

**Email** — recap mail from the senders the register whitelists:

```
uv run <SKILL_DIR>/scripts/email_sweep.py <watermark> <output>
```

**Chat** — every conversation you are a member of, one raw file per
conversation with new messages, listed on stdout by id:

```
python3 <SKILL_DIR>/scripts/chat_export.py <watermark> <output>
```

**Fathom** — the meetings a Fathom API key can see, created since the
watermark: each one's summary and action items and, when the source sets
`"transcripts": true`, its verbatim transcript, written as one meeting file per
meeting:

```
python3 <SKILL_DIR>/scripts/fathom_export.py <watermark> <output>
```

The meeting files go to `inbox/fathom/`, one per meeting.
It lists from the watermark less the source's `lookback_hours` (72 by default),
because Fathom writes a summary some time after it creates the meeting, and the
source's `ledger` of recording ids keeps the overlap from being exported twice.
A meeting whose summary is still empty is counted as not ready, named by
recording id, and left out of the ledger, so the next run within the lookback
exports it. A meeting with any calendar invitee at one of the source's
`excluded_invitee_domains`, or a subdomain of one, is counted, written nowhere,
and has no transcript requested: that list is where a client contract forbidding
AI use of its meetings is recorded, and the source must name it, as `[]` when
there is none. A transcript that comes back empty or not found is written as
`Transcript unavailable.`, and the meeting is exported and named by recording
id. A watermark older than `max_lookback_days` (90 by default) is refused unless
`--allow-backfill` is passed. The key comes from `FATHOM_API_KEY`, or else the
file `credential.key_file` names (`~/.config/fathom/api-key` by default), which
a person stores by running `scripts/fathom_credential.py` from the plugin root
in a terminal.

```
"ledger": "notes/.fathom-ledger",
"lookback_hours": 72,
"excluded_invitee_domains": ["<a client whose contract forbids AI use>"],
"transcripts": true
```

**Notion** — the pages under record-dense locations the register lists as
`covered_locations`, changed since the watermark, and, when the same source lists
`open_locations`, every changed page under neither list:

```
python3 <SKILL_DIR>/scripts/notion_export.py <watermark> <output>
```

It finds the changed pages by search, a few requests for the whole workspace.
Notion's search index is eventually consistent, so an edit can surface hours
after it was made; both search adapters, this one and the sweep below, search
from the watermark less the source's `index_lag_hours` (72 by default) to catch
it, and print the same watermark as ever. The lookback costs a few more search
pages and placement requests; what it finds again is not exported or read twice
when the source names a `ledger`: a small committed file of page ids and the
edit times already processed, so a page already exported or read at its current
edit time is skipped. Give each Notion source its own:

```
"ledger": "notes/.notion-covered-ledger",
"index_lag_hours": 72
```

A source with no ledger processes the whole lookback again every run, and the
adapter says so on stderr. The ledger, like the watermark, is written only by a
run without gaps, and holds ids and times only, never a title.

Add `--walk` to visit every page under every location instead. It costs a
request per block that has children, not per page, since finding child pages
means listing every toggle, list item and column on the way: minutes on a large
location, up to an hour on deeply nested progress logs. It names each location
on stderr as it starts, and each page as its blocks are listed, by position, id,
`children` requests and seconds, never by title. With the lookback catching an
edit the index shows late, the walk remains only the check for an item the index
never shows at all. Run it about monthly, and say in the watermark note when it
last ran.

**Notion sweep** — everything else in the workspace changed since the watermark:
a manifest of id, kind, edit time and title, then **what changed in each listed
page**, read by the page-changes walk below and written into the same file:

```
python3 <SKILL_DIR>/scripts/notion_sweep.py <watermark> <output>
```

It reads every block of every changed page, because Notion moves no edit time on
a block for an edit nested inside it, so no branch can be skipped. That takes
minutes when the changed pages are long. **Run it in the background, never under
a time limit**, and read the one file it writes. It names each page on stderr by
position, id and reading mode as it starts, and its block count and seconds as it
ends, never by title. A page it could not read fully is a gap, like any other.
Each page's blocks are read from the earliest moment an edit to it could have
gone unreported: the minute after the edit time its ledger record holds, or the
start of the lookback without one. A page the index showed late would otherwise
print nothing of its late edit, since a block's own edit time predates the
watermark.

The register shapes the walk four ways. A long page that grows by inserting
each new section above the last goes under `newest_first_pages`, with the number
of top-level `blocks` still being edited, and the walk reads only those, saying
in the output how many older ones it left unread:

```
"newest_first_pages": [{"name": "Weekly reviews", "id": "<page id>", "blocks": 2}]
```

Flat pages — a CRM database whose rows are hundreds of top-level paragraphs —
go under `shallow_locations` by the database or parent page they sit in. Every
page at or under it, at any depth, walks only the top-level blocks edited since
the watermark. Notion moves no edit time on a parent for a nested change, which
is what the full walk is for; a flat page keeps everything at the top level,
where the edit times are reliable. An edit or comment nested under an unchanged
block goes unseen, so keep it to pages that are flat:

```
"shallow_locations": [{"name": "CRM", "id": "<database id>"}]
```

And a location whose pages are touched often but never yield anything goes under
`skipped_locations`. Its changed pages stay in the manifest and are named in a
skipped section, but are not read; a skip is not a gap:

```
"skipped_locations": [{"name": "Recruiting", "id": "<page id>"}]
```

Comments are read only where the register asks for them. A comment moves no edit
time, not even its block's, so finding one means asking every walked block, a
request a block, which more than doubles the walk; and comments rarely carry
anything durable. Notion's page-level comment list leaves out most comments
anchored to blocks, so it cannot stand in for the per-block requests. A page
under `comment_pages`, or at or under a listed page or database, at any depth,
has every walked block and the page itself asked for comments. Every other page
makes no comment request, and its section says so in one line. With no
`comment_pages`, comments are read nowhere:

```
"comment_pages": [{"name": "Design reviews", "id": "<page id>"}]
```

A skip beats all three others: a skipped page is not read, comments included. A
page's own `newest_first_pages` entry beats a shallow location above it.
`comment_pages` combines with either: it decides whether comments are asked
for, and they are asked of the blocks those rules walk.
Only readable pages are shaped by any of this.

**A register can make the sweep default-deny.** Beside `covered_locations`, the
covered source may list `open_locations` in the same shape. Then only a page
under an open location is read; a page under neither list is named by id, never
read, and exported by the `notion` adapter for the gate. The nearest
listed ancestor decides. A page whose ancestry the integration cannot see is
unplaceable, a gap named by id, when open locations are listed or a covered one
cannot be fetched, until the page the integration is shared at is listed.

All five print the output path, then counts, then the new watermark, and send gaps
to stderr. Neither stream carries content, a title, a subject or a person's name:
ids and counts only, with anything worth naming written into the output file.
That is what makes them safe to run from this session directly.

Add `--source <name>` when the register calls a source something other than
`email`, `chat`, `fathom` or `notion`.

**Notion page changes** — the walk the sweep runs on each page, for reading one
page by hand, such as a page someone points at outside a sync:

```
python3 <SKILL_DIR>/scripts/notion_page_changes.py <page id> <watermark>
```

It prints the blocks edited since the watermark, each unchanged ancestor as one
marked line of context, and, on a page `comment_pages` covers, any comment left
since the watermark under the block it sits on, with images and files named rather than linked. A page that
has been appended to weekly for a year comes back as its newest section. Unlike
the adapters its stdout is content, so it reads the register and **refuses a
page under a covered location**, one under no open location when the register
lists them, or one it cannot place, before printing anything; those stay the
`notion` adapter's. Prefer it to fetching a page
through the MCP server, whose markdown carries every block the page has ever
held and a few hundred characters of signed URL per image. It exits 3 when a
comment request failed or blocks nested too deep to read, and names them on
stderr.

**Writing a block** — for an edit the MCP server cannot send. Its
`update-a-block` tool nests the update under a `type` parameter, so Notion never
sees a `table_row` or `paragraph` key and refuses the call; a table row has no
other route. Write the `PATCH /v1/blocks/{id}` body to a file and send it with
the same credential the readers use:

```
python3 <SKILL_DIR>/scripts/notion_update_block.py <block id> <body.json>
```

A table row's update replaces every cell, so list the table's children first and
carry over any cell being left alone. It prints only text lengths.

**Comments are a deliberate blind spot.** On a page outside `comment_pages` a
comment is not asked for, and a comment left on a page nobody edited moves no
edit time, so no search returns the page, listed or not. List a page under
`comment_pages` where its comments are the content — a review thread, a page
whose decisions are made in the margin — and say when a sync's completeness
rests on comments elsewhere; only Notion's webhooks report those.

### What each adapter's run leaves for the gate

**Chat** writes one raw file per conversation, each one batch. When it reports
`0 conversation(s) with new messages` it prints `skip the gate`.

**Notion** writes one side file per changed page, and its export holds only a
placeholder per page naming it by id and edit time, since a title can be a
person's name. A batch is the pages of one location. When nothing changed it
prints `Nothing to digest: skip the gate.`, writes nothing to its folder, and a
quiet window costs Notion API calls and no model tokens. Its watermark is
**inclusive at the minute**, because Notion stamps edits to the minute (rule 2's
exception). **A gap withholds the watermark.** An unreadable location, a
database that couldn't be queried, a page that couldn't be rendered, a search
result that couldn't be placed, or a walked tree deeper than `max_depth` makes
the run exit 3 without printing a new watermark. Keep the old watermark, record
the gap in the watermark note, and let the next run re-cover the window. This is
rule 3 applied correctly: the watermark advances when nothing *changed*, not
when something went unread.

The adapter covers only the listed locations. **The rest of the workspace is the
sweep adapter's**, and it runs as a script for the same reason. A sweep paged
through the MCP server shares one result stream with the record-dense locations,
so a guard withholding their results also stalls the pagination running through
them, and a retry after the refusal reads as a workaround. The sweep searches
over the REST API instead and places each result by its parent chain. A result
under a covered location is only counted, and one under no open location in a
default-deny register only named by id, since the export adapter reads both;
everything else lands in the manifest and is read into the same file. It takes its
exclusions from the covered source it names with `covered_by`, so the register
lists them once. It shares the export's minute-inclusive watermark, and a result
it cannot place withholds the watermark, since it might be record-dense.

**Fathom** writes one meeting file per meeting, each one batch, with the
transcript **verbatim** beside the recap; `references/transcripts.md` has the
measurements and how to read one. The export holds a placeholder per meeting
naming its file, recording id and recorded date. When nothing is ready it prints
`Nothing to digest: skip the gate.` and writes no meeting files. With
`--count-only` the meetings are only counted, no transcript is requested, and
neither the ledger nor the watermark advances. A listing page that could not be
read withholds the watermark and the ledger, like a Notion gap. A transcript that
could not be read, other than one not found, is a gap that takes the run back:
the meeting files it wrote are removed, no export is written, and the next run
re-covers the window. Fathom keeps the original, so a later question re-fetches
one meeting by recording id rather than relying on a pile at rest.

### When an adapter cannot run

Its prerequisites are reported at session start and by
`/dan-knowledge-base:setup`. Do not work around a missing one — skip that
source, finish the rest of the sync, and **record the skip in the watermark
note** (rule 4). Distinguish two cases, because they have different remedies: no
credential at all means setup was never done; a credential present and rejected
means it expired and needs a fresh sign-in.

## References

- `references/note-types.md` — accumulators, snapshots, logs, queues
- `references/sweep-economics.md` — why the sweep costs more than the writing
- `references/adding-a-source.md` — interrogating a new source before trusting it
- `references/configuring-sources.md` — where per-repo configuration lives
- `references/chat-sources.md` — chat, and the split that makes it safe
- `references/digest-brief.md` — what a digest keeps, passed to the covered gate
- `references/transcripts.md` — reading a meeting transcript when distilling
