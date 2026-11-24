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

## A register can require a session

A knowledge base that may only sync inside one kind of session — one whose
launcher sets an environment variable — says so at the top level of the
register:

```json
"session": {"required_variable": "<the variable that session's launcher sets>"}
```

Every adapter then refuses, before any request or write, in a session where the
variable is unset or empty, and session start says in one line that a sync
cannot run there. Without the key, nothing changes.

## What a source needs to be reachable at all

A source with `"adapter": null` is still reached through *something* — an MCP
server, a CLI someone installed once — and nothing about the register says so
unless it is written down. The failure that follows is the quiet one: the
server is absent, the source returns nothing, the sync reports sweeping it, and
the watermark advances over a window nobody read.

`requires` is where the entry names it:

```json
"task-board": {
  "adapter": null,
  "requires": {"mcp": ["clickup"], "commands": ["clickup-cli"]}
}
```

- **`mcp`** — server names whose tools must be present in the session. Checked
  by `/dan-knowledge-base:setup`, which runs where the tool list is visible.
- **`commands`** — executables that must resolve on PATH. Checked at session
  start, because a subprocess can answer that one.

Neither is checked by the sync itself, which would turn a missing prerequisite
into a mid-run failure rather than something known before starting.

Name only what the source genuinely cannot work without. A requirement that is
merely nice to have produces a note on every session that has it, which is how
a check earns itself a reputation for crying wolf.

Everything else in an entry is the adapter's own vocabulary — sender lists for
mail, excluded conversations for chat, excluded invitee domains for Fathom —
and the adapter documents it.

Notion's locations take one key worth knowing before the first sync. A source
whose `covered_locations` list the record-dense pages may also list
`open_locations`, in the same shape:

```json
"open_locations": [{"name": "Engineering wiki", "id": "<page id>"}]
```

Without the key, every page outside a covered location is swept verbatim. With
it, the register is default-deny: only a page under an open location is read,
and a page under neither list is counted, named by id and exported for the
covered gate like a covered one. The nearest listed ancestor decides, so an
open page inside a covered location, or the reverse, works as written. A page
whose ancestry the integration cannot see before it meets a listed location is
read as at the top of the workspace when no open location is listed and the
token can fetch every covered one, since a covered location the token can see
cannot sit above a page it cannot. Otherwise it is unplaceable, a gap, until the
page the integration is shared at is listed.

A value that restricts what may be read at all belongs in the JSON too, where
the adapter enforces it, rather than only in the prose: the chat adapter's
`excluded_conversations`, `dense_conversations` and `private_topic_markers`
(with `marked_conversations` left unset or `"exclude"`) keep a conversation from
being fetched at all, and the `fathom` adapter's
`excluded_invitee_domains` is how a client contract forbidding AI use of its
meetings reaches the script, and the adapter refuses a source that leaves the key
out, so an unrecorded clause stops a run instead of passing through it. The prose
register says which contract each domain comes from.

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
