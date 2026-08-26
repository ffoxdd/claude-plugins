# Configuring sources

A knowledge base's sources are described in **two files with two audiences**,
and keeping the boundary exact is what stops them drifting apart.

| File | Audience | Holds |
|---|---|---|
| `.knowledge-base.json` | scripts | every value a script reads |
| `CLAUDE.md` | the model | why, which notes, traps, decisions |

**The one rule: a value a script reads lives only in the JSON.** The prose
register explains, points, and records what was learned; it never restates a
value. A sender domain written in both places will eventually disagree with
itself, and the copy that is wrong will be the one someone reads.

`config/example.json` in this plugin is a worked example to copy.

## Where the file lives, and why it isn't a plugin setting

`.knowledge-base.json` sits at the root of the knowledge-base repo and is
**committed**. Scripts find it by walking up from the working directory, the
way `.git` is found; its presence is what makes a repo a knowledge base, and
its directory is the root every path inside it resolves against.

Which sources feed a knowledge base is a property of *that repository*, not of
the person at the keyboard: someone can keep two, the config belongs in the
diffs beside the notes it governs, and whoever clones the repo gets a correct
one without setting anything up. A plugin option would put one machine's answer
in front of every repository.

## The shape

Each entry under `sources` is one source. Four fields belong on every one,
each corresponding to a way syncs go wrong silently:

- **`adapter`** — the name of a shipped script, or `null` for a source the
  model queries directly per the register. `null` is not a lesser option: a
  source with a server-side watermark filter and a compact projection needs no
  script at all.
- **`feeds`** — the notes this source writes into. If a source starts writing
  somewhere it doesn't declare, that is worth noticing.
- **`watermark`** — its `format` and its `boundary`, so whoever writes the next
  query knows whether to filter with a strict `>`.
- **`scope_control`** — the container that must come back empty, and what it
  must return, kept here so the proof can be re-run when the query changes.

A source that cannot be listed by recency carries `"reactive": true` and no
watermark, so an empty entry reads as "followed by reference" rather than as a
watermark that has looked stale for months.

Everything else in an entry is the adapter's own vocabulary — sender lists for
mail, dense-conversation names for chat — and the adapter documents it.

## Adding one

`/dan-knowledge-base:add-source` walks the trap list in `adding-a-source.md`
against the live source, proves the scope control, writes the JSON entry and
the prose section together, and seeds the watermark. Doing it by hand is fine
too; what the command buys is that the trap list gets *run* rather than read,
and the register gets written while the answers are in front of you.

## Where a script goes when config can't express it

Configuration is for values. When a source needs *behaviour* no adapter has —
its own pagination shape, a bespoke export format, an internal system with no
general analogue — write a script in the knowledge base's own `scripts/` and
name it in the register.

The line: **an adapter belongs in this plugin when the only things separating
two organizations' use of it are values.** Once one needs different logic, it
has its own script, and both stay simple.
