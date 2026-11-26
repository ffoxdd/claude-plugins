# dan-knowledge-base

Turns a git repository into the place where what your organization knows
accumulates. Meeting recaps, chat threads, ticket changes and wiki edits get read
once, distilled into notes, and committed — while the raw material they came from
stays out of version control.

```
/plugin install dan-knowledge-base@ffoxdd
```

## Using it

In a session whose working directory is inside the knowledge base, ask:

> sync the knowledge base

That loads the skill and runs the whole procedure: read the repo's source
register, list the unprocessed intake in `inbox/`, sweep each live source since
its watermark, distill what changed into the notes that own those subjects,
advance the watermarks, and commit. It pushes only when you ask. If a phrasing
ever misses, "use the knowledge-base skill and sync" is the reliable form.

The same skill loads when you write or correct a note by hand, or ask what the
repository already knows — the sync request is just the most common way in.

So the loop is: drop anything worth keeping into `inbox/` as
`YYYYMMDD_description.ext`, ask for a sync when it suits you, and read the diff.

Three commands are setup-time and rarely typed twice:
`/dan-knowledge-base:init` scaffolds a repository, `/dan-knowledge-base:add-source`
declares a live source and runs the trap list against it,
`/dan-knowledge-base:setup` fixes an adapter's prerequisites.

## What it is

A knowledge base is a git repo in two halves: **raw intake, never committed**,
and **distilled notes, committed**. The plugin carries the method — intake
lifecycle, the note types that decide how each file is updated, watermark
discipline, the trap list for a new source — as a skill loaded on demand rather
than context injected into every session.

It brings no sources of its own. Which systems feed a knowledge base is a
property of one organization, so it lives in that repo, in two files:

| File | Audience | Holds |
|---|---|---|
| `.knowledge-base.json` | scripts | every value a script reads |
| `CLAUDE.md` | the model | why, which notes, traps, decisions |

The skill's `references/configuring-sources.md` covers the contract between them.

## What it ships, and what each costs

| Layer | Needs |
|---|---|
| Method, `/init`, local `inbox/` | nothing |
| A source Claude queries directly | that source's own MCP server or CLI |
| `email` adapter | `uv`; a mail MCP server already signed in |
| `chat` adapter | `uv`; bundled `slack-client`; `playwright`; a captured session |
| `notion` and `notion-sweep` adapters, the page-changes tool | `python3`; the Notion MCP server already configured |
| `fathom` adapter | `python3`; a Fathom API key, in `FATHOM_API_KEY` or a key file |

The `email` adapter and the bundled `slack-client` the `chat` adapter drives are
`uv run --script` files with inline dependencies, so `uv` is the one prerequisite
nothing here installs; `/dan-knowledge-base:setup` walks
through it and the rest. Prerequisites are derived from the register: a
knowledge base that declares no adapters is told nothing, and a declared source
that is not yet working is reported once per session and recorded as skipped in
the watermark file, so the gap stays visible in `git log`.

The `notion` adapter is standard library only. It borrows the Notion MCP server's
own token from Claude Code's config, the way the `email` adapter borrows a mail
server's token cache, so it adds no credential and never prints the one it reads.
It exists for **record-dense Notion locations**: pages a session must not read
directly. It finds the changed pages over the REST API, by search, or by walking
every page with `--walk` as the periodic check, and writes their text only to
side files in a git-ignored folder under the intake directory, for a covered
gate to digest. The `notion-sweep` adapter covers the rest of
the workspace on the same token: a search for what changed that counts, rather
than lists, anything under those locations, and then reads each page it lists
as only its blocks edited since an edit to it could last have gone unreported
(the minute after its ledger record, or the start of the index-lag lookback),
with the comments left since on the pages the register lists for them. The
page-changes tool is that walk for one page by hand, and refuses any page under
those locations. A register that also lists `open_locations` is default-deny:
only pages under those are read, and the rest go the record-dense route.

Every adapter writes only under the intake directory, owner-only, and prints ids
and counts, never a title or a name. `layout.retention_days`, when set, deletes
processed intake older than that at session start.

The `fathom` adapter is standard library only too, and holds the one credential
this plugin asks for: a Fathom API key, read from `FATHOM_API_KEY` or from a key
file that `scripts/fathom_credential.py` writes, readable by its owner alone,
after asking for the key without echo. It lists the meetings the key can see and
writes each one's summary, action items and, when the register asks for them,
verbatim transcript to a meeting file in a git-ignored folder under the intake
directory, one file per meeting, which a covered gate digests where there is one. A meeting with an invitee from a domain the register excludes,
such as a client whose contract forbids AI use of its meetings, is counted,
written nowhere, and has no transcript requested.

**Permissions.** A PreToolUse hook approves the `slack-client` listings
(`channels`, `starred`, `memberships`), which print no message, so installing the
plugin is the grant and `permissions.allow` stays untouched. `history` and
`replies` still prompt, because they print message text into the session; the
adapter runs them as a subprocess and needs no grant. `slack-client login` prompts
too — it opens a browser and waits for a person — as does `slack-client file`,
which saves a message's attachment to a path of the caller's choosing, and any
invocation chaining a second command. Your own `permissions.deny` overrides all
of it.

## The bundled Slack client, stated plainly

The `chat` adapter runs on `slack-client`, shipped in this plugin and reached
through a launcher in its `bin/`, which Claude Code puts on PATH inside a
session. Before adopting it:

- **It authenticates as you, not as an app.** A captured browser session carries
  your entire read access to the workspace. Distributing it to colleagues is a
  separate decision wanting explicit sign-off.
- **It rides Slack's undocumented internal API.** A breaking change arrives
  silently.
- **Its launcher names `uv run --script` rather than trusting the shebang**,
  because `#!/usr/bin/env -S` is not portable to Git Bash on Windows. A test pins
  it.

The full reasoning, and the split that keeps per-person records out of the
session, is in the skill's `references/chat-sources.md`.
