# Configuring sources

A knowledge base's sources are described in **two files with two audiences**, and
keeping the boundary between them exact is what stops them drifting apart.

| File | Audience | Holds |
|---|---|---|
| `.knowledge-base.json` | scripts | every value a script reads |
| `CLAUDE.md` | the model | why, which notes, traps, decisions |

**The one rule: a value a script reads lives only in the JSON.** The prose
register never restates one — it explains, points, and records what was learned.
A sender domain written in both places will eventually disagree with itself, and
the copy that is wrong will be the one someone reads.

`config/example.json` in this plugin is a worked example to copy.

## Where the file lives, and why it isn't a plugin setting

`.knowledge-base.json` sits at the root of the knowledge-base repo and is
**committed**. Scripts find it by walking up from the working directory, the way
`.git` is found; its directory is the root that every path inside it resolves
against.

That is deliberately unlike a per-person plugin option. Which sources feed a
given knowledge base is a property of *that repository*, not of the person at the
keyboard: someone can keep two, the config belongs in the diffs alongside the
notes it governs, and whoever clones the repo gets a correct one without setting
anything up. A plugin option would put one machine's answer in front of every
repository.

## The shape

Each entry under `sources` is one source. Four fields are worth having on every
one, because each corresponds to a way syncs go wrong silently:

- **`adapter`** — the name of a shipped script that handles this source, or
  `null` for a source the model queries directly per the register. `null` is not
  a lesser option: a source with a server-side watermark filter and a compact
  projection needs no script at all.
- **`feeds`** — the notes this source writes into. This is what makes an
  unreviewed sync auditable: if a source starts writing somewhere it doesn't
  declare, that is worth noticing.
- **`watermark`** — its `format` and its `boundary`. Recording that the boundary
  is `inclusive` is what reminds whoever writes the next query to filter with a
  strict `>`, which is the difference between a clean sync and one that
  reprocesses its boundary item forever.
- **`scope_control`** — the container that must come back empty, and what it must
  return. A filter you cannot prove is applied is a filter you should assume
  isn't; this is where the proof is kept so it can be re-run when the query
  changes.

A source that cannot be listed by recency carries `"reactive": true` and no
watermark, so an empty entry reads as "followed by reference" rather than as a
watermark that has looked stale for months.

Everything else in an entry is the adapter's own vocabulary — sender lists for
mail, dense-conversation names for chat — and the adapter documents it.

## Adding one

`/dan-knowledge-base:add-source` runs the interview: it walks the trap list in
`adding-a-source.md` against the live source, proves the scope control, writes
the JSON entry and the prose register section together, and seeds the watermark
so the first sync does not try to backfill all of history.

Doing it by hand is fine too. What the command really buys is that the trap list
gets *run* rather than read, and that the register section gets written while the
answers are still in front of you rather than a week later.

## Where a script goes when config can't express it

Configuration is for values. When a source needs *behaviour* no adapter has —
its own pagination shape, a bespoke export format, an internal system with no
general analogue — write a script in the knowledge base's own `scripts/` and
name it in the register. That is the correct home for it, not a fork of an
adapter here.

The line: **an adapter belongs in this plugin when the only things separating two
organizations' use of it are values.** Once one of them needs different logic, it
has its own script, and both stay simple.
