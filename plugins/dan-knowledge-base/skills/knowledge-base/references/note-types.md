# Note types

Three kinds of note need different behaviour on sync, and getting the kind
wrong is what makes a knowledge base expensive to maintain rather than merely
imperfect. The kind is declared in the note's own frontmatter, so adding a note
never means editing a list somewhere else.

## Accumulator — the default

Every note is an accumulator unless it says otherwise. It is enriched
incrementally and never replaced wholesale: new information is added to the
relevant section, and information now known to be wrong is corrected in place.

No frontmatter is needed to opt in. That matters — the default has to be the
kind that is safe when nobody thought about it, and losing content is worse than
accumulating it.

## Snapshot — replaced whole

```
---
note-type: snapshot
---
```

A snapshot is rewritten entirely each sync, with `Last updated: YYYY-MM-DD` at
the top. **It describes only what is true now.**

That constraint is the whole point, and it is the one most often violated by
accident. A snapshot carries no dated update-chains (`**Update (7/27):** …`), no
"new this week / carried forward from last week" scaffolding, and no
struck-through resolved items. All of that is chronology, and a snapshot that
accumulates chronology stops being a snapshot: it grows without bound, and every
sync then pays to read the entire history in order to amend a few lines. That
cost compounds — it is why the distinction is worth enforcing rather than
treating as a style preference.

So: when a fact in a snapshot changes, **overwrite it**. When an item stops
being current, **delete it**.

Individual facts still carry their source and date, per the provenance
convention. Attribution is not chronology: "confirmed by <person>, <date>" is a
property of the fact as it stands now, while "was X, became Y on the 14th" is a
history, and only the first belongs here.

## Log — append-only

```
---
note-type: log
---
```

New entries go at the top, newest first, and an entry is never revised once
written.

A log is cheap for a reason worth naming: **it is never read in order to be
written.** A new entry is inserted at the top without loading what came before,
so its cost per sync is constant no matter how long it gets. And nothing in a
log rots, because every entry is a timestamped statement of what was true when
written and was never meant to stay current.

## The snapshot/log pair

The two work together, and the pairing is the standard answer to "where does
this go":

- a **snapshot** for current state — who is on what, which workstreams are live,
  what the present configuration is
- a **log** beside it for the chronology — what happened, what was decided, what
  shipped, what got resolved

On a sync, **append the new dated entry to the log, then correct the snapshot in
place**, deleting whatever the new information retires. The log is why the
snapshot is allowed to forget: nothing is lost by deleting a retired item from
current state, because the dated record of it exists next door.

## Queue — a companion to an expensive document

A queue is a companion note to some other, higher-effort output document.
Incoming points accumulate in a **Pending points** section as they arrive; a
dedicated synthesis session folds the relevant ones into the output document and
then clears that section. A leading **Standing orders** section — steering rules
for the output document, such as its audience and framing constraints —
persists across clears.

Use a queue when updating the output document is expensive enough that inputs
need to batch rather than trigger an update each time: a document reserved for
the most capable model, a generated deck, anything with a build step or a human
review gate. The queue converts a stream of small interruptions into one
scheduled piece of work, and the standing orders are what keep the synthesis
session from re-deriving the document's constraints every time.

Record the pairing explicitly in the register — which queue folds into which
document — since neither file can be understood alone.
