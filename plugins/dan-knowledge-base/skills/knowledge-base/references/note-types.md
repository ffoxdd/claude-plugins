# Note types

Three kinds of note need different behaviour on sync, and getting the kind
wrong is what makes a knowledge base expensive to maintain rather than merely
imperfect. The kind is declared in the note's own frontmatter, so adding a note
never means editing a list elsewhere.

## Accumulator — the default

Every note is an accumulator unless it says otherwise: enriched incrementally,
never replaced wholesale. New information goes into the relevant section, and
information now known to be wrong is corrected in place. No frontmatter opts
in — the default has to be the kind that is safe when nobody thought about it,
and losing content is worse than accumulating it.

## Snapshot — replaced whole

```
---
note-type: snapshot
---
```

Rewritten entirely each sync, with `Last updated: YYYY-MM-DD` at the top. **It
describes only what is true now.**

That constraint is the one most often violated by accident. A snapshot carries
no dated update-chains (`**Update (7/27):** …`), no "new this week / carried
forward" scaffolding, and no struck-through resolved items. All of that is
chronology, and a snapshot that accumulates it grows without bound, so every
sync pays to read the entire history in order to amend a few lines.

So: when a fact changes, **overwrite it**. When an item stops being current,
**delete it**.

Individual facts still carry their source and date. Attribution is not
chronology: "confirmed by <person>, <date>" is a property of the fact as it
stands now; "was X, became Y on the 14th" is a history, and only the first
belongs here.

## Log — append-only

```
---
note-type: log
---
```

New entries go at the top, newest first, and an entry is never revised once
written. A log **is never read in order to be written** — a new entry is
inserted without loading what came before, so its cost per sync is constant —
and nothing in it rots, because every entry is a timestamped statement of what
was true when written.

## The snapshot/log pair

The standard answer to "where does this go":

- a **snapshot** for current state — who is on what, which workstreams are
  live, the present configuration
- a **log** beside it for chronology — what happened, what was decided, what
  shipped, what got resolved

On a sync, **append the dated entry to the log, then correct the snapshot in
place**, deleting whatever the new information retires. The log is why the
snapshot is allowed to forget.

## Queue — a companion to an expensive document

A queue is a companion note to a higher-effort output document. Incoming
points accumulate in a **Pending points** section; a dedicated synthesis
session folds the relevant ones into the output document and clears the
section. A leading **Standing orders** section — audience, framing constraints
— persists across clears.

Use one when updating the output document is expensive enough that inputs need
to batch: a document reserved for the most capable model, a generated deck,
anything with a build step or a human review gate. Record the pairing in the
register — which queue folds into which document — since neither file can be
understood alone.
