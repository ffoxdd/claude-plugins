---
name: knowledge-base
description: Working in a knowledge-base repo — one that distills live sources (meeting recaps, task trackers, wikis, chat, git history) into committed notes. Carries the intake lifecycle, watermark discipline, the note types that decide how each file gets updated, and the sync procedure. Use when asked to sync, refresh, or integrate intake; when writing into such a repo; or when setting one up.
---

# The knowledge-base pattern

A git repo in two halves: **raw intake, never committed**, and **distilled
notes, committed**. Nearly everything below follows from that split.

The pattern earns its keep by making organizational knowledge greppable and
reviewable. "What do we know about X" is answered from local files in one
`grep`; how the answer changed is in `git log`; and a claim can be traced to
the source and date that produced it. No API call, and no dependence on a
source that has since been reorganized out from under the answer.

**This skill does not know your sources, and shouldn't.** Which systems feed a
knowledge base, how each is queried, and the traps each one hides are
properties of one organization. They belong in the knowledge-base repo's own
`CLAUDE.md` — which Claude Code loads for you when you work in that repo — as a
register of sources. `references/adding-a-source.md` is what to put there and
how to interrogate a new source before trusting it, and
`references/configuring-sources.md` covers the split between the values scripts
read and the reasoning they don't. Everything in this file is the part that is
the same everywhere.

If the repo doesn't exist yet, `/dan-knowledge-base:init` scaffolds one.

## Layout

```
inbox/             raw intake — gitignored
inbox/processed/   intake already distilled — gitignored
notes/             distilled knowledge — committed
notes/.sync-state  per-source watermarks — committed
```

**Intake is flat, and the filename carries the organization:**
`YYYYMMDD_description.ext`, with a source prefix where the source isn't obvious
(`20260716_chat_billing-thread.txt`). Per-source subdirectories look tidier and
cost more than they're worth: they fragment the unprocessed queue across
directories, and the queue is the one thing you need to see whole. A filename
prefix does a folder's job without that cost.

**The unprocessed queue is a set difference** — whatever is in `inbox/` and not
in `inbox/processed/`. Moving a file after distilling it is what marks it done.
There is no status field to maintain, and therefore no way for the marker to
drift out of agreement with reality.

**Raw intake is never committed**, and each of three reasons would be enough on
its own. It is an order of magnitude larger than what it yields. It rots — a
transcript six months old is worth nothing beside the conclusion drawn from it.
And it is the material most likely to carry something that should never enter a
repo: personal data, a credential pasted into a chat log, a third party's
numbers. Gitignoring the whole intake tree is also what makes it safe to pull
*anything* in, because the pull stops being a publication decision.

## Self-authored capture is an input, not a section

If you keep a journal, a daily log, or any other raw personal capture, it is a
**source** like anything arriving from outside, and it belongs outside `notes/`.
Whether you keep one at all is a personal practice this pattern has no opinion
about, which is why nothing here scaffolds a place for it.

Two things follow if you do. A grep for what the organization knows should not be
reading half-thoughts and todos, so keep it out of `notes/` sweeps. And when an
entry turns out to be durable, **promote it** into the note that owns that
subject rather than copying it — the capture keeps whatever didn't graduate, and
is not a second copy of the record.

## Note types decide how a note is updated

Every note in `notes/` is an **accumulator by default** — enriched in place,
never replaced wholesale. Two other kinds declare themselves in the note's own
frontmatter: `note-type: snapshot` (rewritten whole each sync, describing only
what is true now) and `note-type: log` (append-only, newest first, entries never
revised). Check the frontmatter of the note in front of you rather than a list
kept somewhere central — a central list needs an edit every time a note is
added, which is exactly the maintenance the frontmatter convention removes.

Full semantics, why a snapshot must not accumulate chronology, how a
snapshot/log pair works together, and the queue pattern for expensive output
documents: `references/note-types.md`.

## Watermark discipline

Four rules, each of which exists because the failure it prevents is silent.

1. **Read the clock before you query, and make that reading the next
   watermark** — not the newest returned item's timestamp. Two reasons. A
   compact list projection often omits timestamps entirely, so the newest value
   isn't in the response to read. And an item modified between your clock
   reading and the query gets re-reported next sync instead of skipped;
   re-reporting is cheap and visible, skipping is neither.

2. **Establish whether the source's boundary is inclusive.** Plenty of APIs
   treat a watermark as `>=`, which re-delivers the boundary item on every
   single sync forever. Filter with a strict `>` yourself rather than trusting
   the parameter's name.

3. **Advance the watermark even when nothing changed, and write down why it
   didn't change.** A genuinely quiet source and a silently broken query
   produce the identical result in a file that records only timestamps. The
   note is the whole difference: "nothing above the prior watermark; asserted by
   re-running with an older one, which returned the known items" is evidence,
   and a bare timestamp is not.

4. **A source deliberately skipped gets a note too**, for the same reason — so
   the next sync can tell a decision from an omission.

## The sync procedure

**A request is what starts a sync** — "sync the knowledge base", "pull in what's
new", "integrate the inbox" — and this skill is the whole workflow it runs. Asked
how to run one, say the phrase and what it does to the repo: distills the new
material into notes, advances the watermarks, commits, and leaves the push.

When asked to sync, refresh, or integrate intake:

1. **Read the repo's source register** (its `CLAUDE.md`) for which sources
   exist, how each is queried, and what each watermark's format is.
2. **List the unprocessed queue** — in `inbox/`, not in `inbox/processed/`.
3. **Read `notes/.sync-state`.** Anything older than roughly a day is worth
   syncing.
4. **Record the wall clock now, per source, before querying it** (rule 1).
5. **Sweep for what changed, cheaply** — see `references/sweep-economics.md`.
   Then fetch in full only the items the sweep says are substantive.
6. **Distill each item into the right note(s)**, checking each note's
   frontmatter for its type: insert a dated entry at the top of a log without
   reading the rest of it; rewrite a snapshot whole, deleting what the new
   information retires; add to or correct the relevant section of an
   accumulator.
7. **Move each processed intake file to `inbox/processed/`.**
8. **Write the new watermarks**, with a per-source note — including the
   no-change and the skipped ones.
9. **Commit without asking. Push only when asked.**

Step 9 is a deliberate asymmetry. A sync is routine, frequent, and its whole
output is a diff in a repo: a wrong commit costs an amend, while a confirmation
prompt on every sync costs more than the mistakes it prevents. Pushing is what
makes a mistake expensive to undo, so that stays a request.

## Provenance is per-fact, and not optional

When a fact enters a note, record where it came from and when — the person and
date who confirmed it, or the source and its date. Without it a note degrades
into a pile of undated assertions that nobody can re-check or age out, and the
first contradiction between two of them is unresolvable.

Provenance is attribution, and it is not the same thing as chronology. A
snapshot carries the first and must not accumulate the second;
`references/note-types.md` covers why.

## Navigation is the directory tree, not cross-links

Organize notes into folders, with filenames clear enough that things are found
by browsing. Don't maintain a hand-written index or a dense web of inter-note
links: both rot silently, and both turn moving one note into edits scattered
across many. Cross-link only for a genuinely non-obvious relationship — a
specific upstream/downstream dependency — and at most once per note per target.

## Searching notes/

One case-insensitive multi-pattern call rather than one call per term:

```
grep -rn -i -e pattern-one -e pattern-two notes/
```

**A search returning nothing is not evidence the topic is absent.** Company,
product, and person names are routinely misspelled by whatever captured them —
a transcription pass will render an unfamiliar name phonetically, and that
spelling is what landed in the note. Try the spellings a speech-to-text pass
would produce before concluding the knowledge base doesn't have it.

## Sources that mix durable content with personal records

Some sources carry both in one body: an operations log where standing policy is
written between per-person rows, a support channel where the useful pattern is
surrounded by the cases that revealed it. Reading one directly pulls those
records into the session for content that was only ever going to be committed
as aggregates.

The shape that resolves it splits the work in two:

- **A deterministic script does the mechanical half** — fetch, dedupe, group —
  and writes raw content only to gitignored paths. Its *stdout* stays clean by
  construction: a path, a count, a new watermark. So running it exposes
  nothing, and the main session can run it itself.
- **A model does the judgment half**, under whatever isolation your
  organization requires, reading those files and returning **structural facts
  only**: policies, mechanics, defect patterns with counts, named business
  entities. Never the records themselves.

Two things make that more than a gesture. The judgment half is the only half
that reads raw content, so it is the only half needing the isolation — which
makes the isolated agent's tool surface small enough to be worth constraining
(reading and editing files, running nothing). And the raw files are scratch:
deleting them once the summaries are written is part of the procedure, not a
tidy-up afterwards.

Chat is the hardest instance of this and the one worked out in most detail —
membership-scoped enumeration, tiering driven by the platform's own privacy
flags, and where the isolated agent's own permission classifier gets in the way:
`references/chat-sources.md`.

If your organization has a covered or zero-retention endpoint for this, the
`dan-work-routing` plugin in this marketplace carries the escalation ladder and an
agent to delegate to. If it has some other boundary, the same split applies
across that one.

## Running the shipped adapters

Two adapters ship with this skill, in the `scripts/` directory **beside this
file**. Invoke them by absolute path, built from the directory this skill was
loaded from — written below as `<SKILL_DIR>`. Never guess or hardcode that path:
it carries a version that changes on every plugin update, so a remembered one
goes stale silently.

An adapter reads the register itself, from the working directory, so the only
arguments are the watermark and where to write.

**Email** — digest mail from the senders the register whitelists. It has
dependencies, so it runs under `uv`:

```
uv run <SKILL_DIR>/scripts/email_sweep.py <watermark> <output>
```

**Chat** — every conversation you are a member of, tiered by privacy:

```
python3 <SKILL_DIR>/scripts/chat_export.py \
  <watermark> <output> --sensitive-raw-directory <scratch>/raw
```

Both print the output path, then counts, then the new watermark, and send gaps to
stderr. That stdout contract is what makes them safe to run from this session
directly: no message content passes through it.

Add `--source <name>` when the register calls a source something other than
`email` or `chat`.

### The chat sequence, which is not one step

1. **This session runs the script.** Its stdout is clean by construction.
2. **An isolated agent edits the file** — replacing each record-dense section's
   placeholder with a structural-facts-only summary read from the side file that
   placeholder names, and gating the rest for stray personal data. Give it file
   reading and editing only; it must run no commands. `references/chat-sources.md`
   explains why that constraint is what makes the arrangement work at all.
3. **This session deletes the side files**, then treats the export as ordinary
   intake.

### When an adapter cannot run

Its prerequisites are reported at session start and by
`/dan-knowledge-base:setup`. Do not work around a missing one — skip that source,
finish the rest of the sync, and **record the skip in the watermark note**, which
is what keeps the gap visible in the repo rather than only in a session someone
scrolled past.

Distinguish two cases in that note, because they have different remedies: no
credential at all means setup was never done, while a credential that is present
and rejected means it expired and needs a fresh sign-in.

## References

- `references/note-types.md` — accumulators, snapshots, logs, queues
- `references/sweep-economics.md` — why the sweep costs more than the writing
- `references/adding-a-source.md` — interrogating a new source before trusting it
- `references/configuring-sources.md` — where per-repo configuration lives
- `references/chat-sources.md` — chat, and the split that makes it safe
