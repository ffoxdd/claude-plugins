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
   re-reported next sync (cheap, visible) instead of skipped (neither).

2. **Establish whether the source's boundary is inclusive.** Many APIs treat a
   watermark as `>=` and re-deliver the boundary item on every sync forever.
   Filter with a strict `>` yourself.

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

Two adapters ship in the `scripts/` directory **beside this file**. Invoke them
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

Both print the output path, then counts, then the new watermark, and send gaps
to stderr. No message content passes through stdout, which is what makes them
safe to run from this session directly.

Add `--source <name>` when the register calls a source something other than
`email` or `chat`.

### The chat sequence, which is not one step

1. **This session runs the script.**
2. **An isolated agent edits the file** — replacing each record-dense section's
   placeholder with a structural-facts-only summary read from the side file that
   placeholder names, and gating the rest for stray personal data. Give it file
   reading and editing only; it must run no commands, and
   `references/chat-sources.md` explains why that constraint is what makes the
   arrangement work.
3. **This session deletes the side files**, then treats the export as ordinary
   intake.

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
