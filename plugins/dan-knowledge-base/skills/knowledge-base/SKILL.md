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
intake.** An adapter whose files an isolated agent must edit in place writes
them there, as the Fathom adapter does to `inbox/fathom/`, because the agent's
file tools are confined to the repository and the intake tree is already
gitignored. Those files never join the queue or `inbox/processed/`; the sync
deletes them once it is done with them.

**Raw intake is never committed.** It is an order of magnitude larger than what
it yields, it rots, and it is the material most likely to carry what must never
enter a repo — personal data, a pasted credential, a third party's numbers.
Gitignoring the whole intake tree is what makes pulling *anything* in safe,
because the pull stops being a publication decision.

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

The shape that resolves it splits the work in two:

- **A deterministic script does the mechanical half** — fetch, dedupe, group —
  writing raw content only to gitignored paths, with a stdout that carries no
  content. The main session can run it itself.
- **A model does the judgment half**, under whatever isolation your
  organization requires, reading those files and returning **structural facts
  only**: policies, mechanics, defect patterns with counts, named business
  entities. Never the records themselves.

The judgment half is the only half reading raw content, so it is the only half
needing isolation — which makes the isolated agent's tool surface small enough
to constrain (reading and editing files, running nothing). The raw files are
scratch: deleting them once the summaries are written is part of the procedure.

Chat is the hardest instance and the one worked out in most detail:
`references/chat-sources.md`. Where your organization has a covered or
zero-retention endpoint, the plugin that governs it defines the isolation the
judgment half runs under.

## Running the shipped adapters

Five adapters ship in the `scripts/` directory **beside this file**. Invoke them
by absolute path built from the directory this skill was loaded from — written
below as `<SKILL_DIR>`. Never hardcode or remember that path: it carries a
version that changes on every plugin update.

An adapter reads the register itself, from the working directory, so the only
arguments are the watermark and where to write.

**Email** — digest mail from the senders the register whitelists:

```
uv run <SKILL_DIR>/scripts/email_sweep.py <watermark> <output>
```

**Chat** — every conversation you are a member of, tiered by privacy:

```
python3 <SKILL_DIR>/scripts/chat_export.py \
  <watermark> <output> --sensitive-raw-directory <scratch>/raw
```

**Fathom** — the meetings a Fathom API key can see, created since the
watermark: each one's summary and action items and, when the source sets
`"transcripts": true`, its verbatim transcript, written as one meeting file per
meeting:

```
python3 <SKILL_DIR>/scripts/fathom_export.py \
  <watermark> <output> --sensitive-raw-directory inbox/fathom
```

`inbox/` stands for the intake directory the register's `layout` names. The
meeting files are scrubbed in place by an isolated agent whose file tools are
confined to the repository, so the directory is inside it and git-ignored; one
inside a work tree that git does not ignore, or that git cannot judge, is
refused before any request.
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
`covered_locations`, changed since the watermark:

```
python3 <SKILL_DIR>/scripts/notion_export.py \
  <watermark> <output> --sensitive-raw-directory <scratch>/raw
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
Covered locations are excluded before any of this.

All five print the output path, then counts, then the new watermark, and send gaps
to stderr. No message content passes through stdout, which is what makes them
safe to run from this session directly.

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
page under a covered location**, or one it cannot place, before printing
anything; those stay the `notion` adapter's. Prefer it to fetching a page
through the MCP server, whose markdown carries every block the page has ever
held and a few hundred characters of signed URL per image. It exits 3 when a
comment request failed or blocks nested too deep to read, and names them on
stderr.

**Comments are a deliberate blind spot.** On a page outside `comment_pages` a
comment is not asked for, and a comment left on a page nobody edited moves no
edit time, so no search returns the page, listed or not. List a page under
`comment_pages` where its comments are the content — a review thread, a page
whose decisions are made in the margin — and say when a sync's completeness
rests on comments elsewhere; only Notion's webhooks report those.

### The chat sequence, which is not one step

1. **This session runs the script.**
2. **An isolated agent edits the file** — replacing each record-dense section's
   placeholder with a structural-facts-only summary read from the side file that
   placeholder names, and gating the rest for stray personal data. A described
   case counts as personal data even without a name in it (the rule is written
   out in the Fathom sequence's step 2), and that holds for every gate,
   Notion's included. Give it file
   reading and editing only; it must run no commands, and confirm that its
   launcher *enforces* that rather than merely recording it —
   `references/chat-sources.md` explains why the constraint is what makes the
   arrangement work, and why an allow list is usually not the control that
   imposes it.
3. **This session deletes the side files**, then treats the export as ordinary
   intake.

When the script reports `0 conversation(s) with new messages`, it also prints
`skip the isolated agent`. The export then holds no message text, so step 2 has
nothing to gate and does not run.

The Notion export runs the same three steps, **except when nothing changed**.
Then the script prints `Nothing to summarize: skip the isolated agent.`, writes
no side files, and step 2 does not run. A quiet window costs Notion API calls
and no model tokens, covered or otherwise. Finding what changed is a script,
and only a changed page's text ever reaches a model.

Otherwise the steps are the same. The one difference is the export:
it holds nothing but placeholders, one per changed page, naming the page by id
and edit time. A title can be a person's name, so every word of a page reaches
only its side file. Its watermark is **inclusive at the minute**, because Notion
stamps edits to the minute, and a strict comparison against a seconds-precision
clock would lose an edit made in the same minute as the query (rule 2's
exception). **A gap withholds the watermark.** An unreadable location, a
database that couldn't be queried, a page that couldn't be rendered, a search
result that couldn't be placed, or a walked tree deeper than `max_depth` makes
the run exit 3 without printing a new watermark.
Keep the old watermark, record the gap in the watermark note, and let the next
run re-cover the window. This is rule 3 applied correctly: the watermark advances
when nothing *changed*, not when something went unread.

The adapter covers only the listed locations. **The rest of the workspace is the
sweep adapter's**, and it runs as a script for the same reason. A sweep paged
through the MCP server shares one result stream with the record-dense locations,
so a guard withholding their results also stalls the pagination running through
them, and a retry after the refusal reads as a workaround. The sweep searches
over the REST API instead and places each result by its parent chain. A result
under a covered location is only counted, since the export adapter reads it, and
everything else lands in the manifest and is read into the same file. It takes its
exclusions from the covered source it names with `covered_by`, so the register
lists them once. It shares the export's minute-inclusive watermark, and a result
it cannot place withholds the watermark, since it might be record-dense.

### The Fathom sequence

A transcript is passed **verbatim**, with the recap beside it, because the only
safe edit to one is removing personal data; `references/transcripts.md` has the
measurements and how to read one. The meeting files are working files, not
intake: the export, which holds only a placeholder per meeting naming its file,
recording id and recorded date, is the intake record. Each meeting file opens
with the line `UNGATED: not to be read until the isolated agent has scrubbed
it`.

1. **This session runs the script**, with `--sensitive-raw-directory` pointing
   at the intake directory's `fathom/` subdirectory (`inbox/fathom/` under the
   default layout), because the isolated agent edits the files in place and its
   file tools are confined to the repository.
2. **The isolated agent gates each meeting file in place, one run per meeting
   file**, with file reading and editing only. It first decides what kind of
   meeting it is:
   - **Case-dense**, where the meeting mostly walks through individual people's
     situations one by one (a clinic's monthly ops review, a support escalation
     call). The agent replaces the whole transcript with a summary of structural
     facts only: policies, mechanics, decisions and owners, and defect patterns
     with counts. The summary's first line names it as one. A scrub cannot make
     such a meeting safe, because the cases are the content.
   - **Any other meeting** is scrubbed. The agent replaces every mention that
     identifies an individual who is not speaking as a colleague, and any named
     person's own care, health detail or membership whatever their role,
     colleagues and business contacts included, with a neutral phrase such as "a
     member". **A case is identifying without a name.** A passage that describes
     one person's situation is rewritten as a generic case ("one member whose
     dependent was missing"): dates finer than the year tied to that person, an
     age, family make-up, the person's employer or group tied to the case, and
     life events (a name change, a move, a death). Taking out the name and
     identifiers while leaving that story does not de-identify it. The agent
     changes nothing else: no rewording, no summarizing, no correcting a garbled
     passage, and every other word, number, speaker label and business name
     stays as written.

   Its last edit replaces the `UNGATED:` first line with `Gated.` Run it on the
   strongest model the covered launcher offers: this is the step that keeps
   personal data out of the session, and it is not where a sync saves money.
3. **A second isolated run checks each gated file**, under the same isolation,
   with fresh context and file reading and editing only. It reads the file and
   looks only for what the gate missed: any passage that still identifies or
   describes an individual by the rule above. If it finds none, its one edit
   replaces the `Gated.` first line with `Verified.` If it finds any, it edits
   nothing and reports each finding by line number and category, never the
   content. That file goes back to step 2 with the findings named, then to this
   check again. A checker is reliable where a self-check is not because it never
   saw the gate's reasoning. Its cost is about the gate's again, and it is not
   where a sync saves money either.
4. **This session confirms every meeting file starts with `Verified.`**, with a
   search that prints filenames only (`grep -L '^Verified\.'`, never content),
   re-runs steps 2 and 3 on any that don't, and only then hands the files on.
5. **This session does not read the transcripts itself.** It hands each day's
   meeting files to a sub-agent on the session's own model, which reads each
   file once and returns only the durable knowledge, following
   `references/transcripts.md`. A transcript held in the main context is re-sent
   on every later turn of the sync. And the sub-agent is not a cheaper model:
   it writes the notes, and a weaker reader reintroduces the attribution errors
   the verbatim transcript exists to avoid. **Its brief includes a stop rule.**
   If a file still describes an individual's case, the reader stops reading
   that file, carries nothing from it, and reports only the filename and the
   category. That meeting goes back through steps 2 and 3, and whoever is
   responsible for the data hears about it, because this reader runs outside the
   isolation and has already seen what it read.
6. **Once the sub-agents have returned their notes, this session deletes the
   meeting files**, and moves the export to `inbox/processed/` like any other
   intake. A scrubbed transcript still holds whatever the scrub missed, and
   Fathom keeps the original, so a later question re-fetches one meeting by
   recording id rather than relying on a pile at rest.

When nothing is ready the script prints `Nothing to summarize: skip the isolated
agent.`, writes no meeting files, and steps 2 to 6 do not run. Without
`--sensitive-raw-directory` the meetings are only counted, no transcript is
requested, and neither the ledger nor the watermark advances. A listing page
that could not be read withholds the watermark and the ledger, like a Notion
gap. A transcript that could not be read, other than one not found, is a gap
that takes the run back: the meeting files it wrote are removed, no export is
written, and the next run re-covers the window.

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
- `references/transcripts.md` — reading a meeting transcript when distilling
