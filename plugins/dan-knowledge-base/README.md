# dan-knowledge-base

Turns a git repository into the place where what your organization knows
accumulates. Meeting recaps, chat threads, ticket changes and wiki edits get read
once, distilled into notes, and committed — while the raw material they came from
stays out of version control.

## The workflow: ask for a sync

Syncing is a request, made in a session whose working directory is inside the
knowledge base:

> sync the knowledge base

"pull in what's new", "refresh the notes", and "integrate the inbox" reach the
same place — the skill names those verbs, so the request is what loads it and the
procedure it carries is what runs. From there, without further prompting from
you:

1. It reads the repository's source register — `CLAUDE.md` for the reasoning,
   `.knowledge-base.json` for the values — so it knows which sources exist and
   how each is queried.
2. It lists the unprocessed intake: whatever is in `inbox/` and not in
   `inbox/processed/`.
3. Per source, it reads the clock, sweeps cheaply for what changed since that
   source's watermark, and fetches in full only what the sweep says is
   substantive.
4. It distills each item into the notes that own those subjects, moves the
   processed intake aside, and writes the new watermarks with a note per source —
   including the ones that had no changes and the ones it skipped.
5. **It commits the result without asking, and pushes only when you ask.** That
   asymmetry is deliberate: a sync is routine and its whole output is a
   reviewable diff, so a wrong commit costs an amend, while a confirmation prompt
   on every sync costs more than the mistakes it prevents. Pushing is what makes
   a mistake expensive to undo, so that stays a request.

So the loop is: drop anything worth keeping into `inbox/` as
`YYYYMMDD_description.ext`, ask for a sync when it suits you, and read the diff.

**A request rather than a keystroke, because the same method covers more than
syncing.** Asking is also what pulls the method in when you write a note by hand,
correct one, or ask what the repository already knows about something — work
nobody would think to announce. And a sync turns on judgment throughout: which
sources are worth sweeping, what in an item is durable, which note owns it. All
of that is read fresh from the repository each time, so what starts it is a
sentence about intent. Naming the skill outright — "use the knowledge-base skill
and sync" — is the reliable form if a phrasing ever misses.

The three commands are setup-time and you will rarely type them twice:
`/dan-knowledge-base:init` scaffolds a repository, `/dan-knowledge-base:add-source`
declares a live source, `/dan-knowledge-base:setup` fixes an adapter's
prerequisites.

## What it does

Adds a skill Claude loads when you are working in such a repository, three
commands you run while setting one up, and two optional adapters that fetch from
mail and chat. It brings no sources of its own: which systems feed a knowledge
base is described in that repository, not here.

A knowledge base here is a git repo in two halves: **raw intake, never
committed**, and **distilled notes, committed**. The plugin carries the method —
the intake lifecycle, the note types that decide how each file gets updated,
watermark discipline, and the trap list to run against a new source — as a skill
that loads when you are working in such a repo rather than context injected into
every session.

**It brings no sources of its own, and that is the design.** Which systems feed a
knowledge base is a property of one organization, so it lives in the repo, in two
files with two audiences:

| File | Audience | Holds |
|---|---|---|
| `.knowledge-base.json` | scripts | every value a script reads |
| `CLAUDE.md` | the model | why, which notes, traps, decisions |

A value a script reads lives *only* in the JSON; the prose never restates one.
`.knowledge-base.json` is also the marker — its presence is what makes a repo a
knowledge base, found by walking up from the working directory the way `.git`
is, and its directory is the root every path inside it resolves against. It is
deliberately not a plugin setting: which sources feed a given knowledge base
belongs in that repo's diffs, and is already correct for whoever clones it.

## What it ships, and what each costs

| Layer | Needs |
|---|---|
| Method, `/init`, local `inbox/` | nothing |
| A source Claude queries directly | that source's own MCP server or CLI |
| `email` adapter | `uv`; a mail MCP server already signed in |
| `chat` adapter | `uv`; bundled `slack-client`; `playwright`; a captured session |

**`uv` is the one prerequisite this plugin cannot work around**, and nothing here
installs it: both adapters are `uv run --script` files with inline dependencies
(PEP 723), which is exactly what lets them ship with no install step of their
own. Astral's standalone installer is the route they promote:

```
# macOS, Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1|iex"
```

Confirm with `uv --version`. Session start reports it missing only if the
register declares a source that needs it.

The two adapters live in the skill's own `scripts/` directory and are invoked by
absolute path from wherever the skill was loaded — the pattern the official Figma
plugin uses for its bundled scripts, and the reason nothing here needs to put them
on PATH. `slack-client` is the exception, because a *person* runs it:
`slack-client login` opens the browser flow — on Windows from Git Bash, since the
launcher is a `#!/bin/sh` file and PowerShell has no way to run one — and telling
someone to type a
version-stamped cache path would be absurd. It gets its name from a launcher in
the plugin's `bin/`, which Claude Code adds to PATH for every installed plugin —
so nothing is written into your home directory and nothing needs re-pointing when
the version stamp changes. That PATH entry exists inside a Claude session, which
is where `/dan-knowledge-base:setup` runs the login from — and running it there is
the point, since the session is where the name resolves at all.

**No allowlist rule is needed.** A PreToolUse hook approves the reads a sync runs
— `channels`, `starred`, `memberships`, `history`, `replies` — so installing the
plugin is the grant and `permissions.allow` stays untouched. A sync that stopped
every few calls for a permission prompt was a poor fit for a plugin whose whole
proposition is an unattended sweep.

`login` is not approved, and that is the same distinction as above: it opens a
browser and waits up to five minutes for a person, so approving it would let an
unattended run launch a browser and hang on it. The grant also refuses anything
that could reach a second command — the invocation is tokenized, and a shell
operator anywhere in it disqualifies the whole thing.

Your own `permissions.deny` still overrides all of it, measured rather than
assumed: a child refused a command its settings denied while a hook approved it.

**Prerequisites are derived from the register, never from what the plugin
ships.** A knowledge base that only processes files dropped into `inbox/` by hand
declares no adapters and is told nothing — the same principle `dan-work-routing`
applies to warehouse CLIs. The session-start check also says nothing at all
outside a knowledge base, since config discovery already answers whether you are
in one.

For a source that *is* declared but not yet working, the skip is not silent: it
is reported once per session, and the sync records it in the watermark file, so a
source skipped for three weeks leaves three weeks of notes in `git log` rather
than one banner you scrolled past. `/dan-knowledge-base:setup` fixes them one at a
time; `/dan-knowledge-base:add-source` declares a new one and runs the trap list
against it while the answers are still in front of you.

## The bundled Slack client, stated plainly

The `chat` adapter runs on `slack-client`, a single-file `uv` script shipped in
this plugin and reached through the launcher in its `bin/`, the same way
`dan-work-routing` ships its covered runner. Three things about it are worth knowing
before adopting it, none of which the code will tell you at the point of
failure:

- **It authenticates as you, not as an app.** A captured browser session carries
  your entire read access to the workspace; nothing about the export narrows it.
  An installed app with scoped permissions is the better arrangement where you
  can get one — this exists for where you cannot, which is why it was written.
  Distributing it to colleagues is a different decision from one person using it,
  and wants an explicit sign-off rather than an inference.
- **It rides Slack's undocumented internal API**, the one the web client uses. No
  compatibility guarantee, and a breaking change arrives silently.
- **Its launcher names `uv run --script` rather than trusting the script's own
  shebang.** `#!/usr/bin/env -S uv run --script` needs a GNU `-S`, and Git Bash on
  Windows is not worth betting the adapter on. Getting this wrong resolves cleanly
  and then dies at `import playwright` — a correct-looking command with a broken
  interpreter, whose failure reads as a missing dependency. A test pins it.

The handling of sources that mix durable content with per-person records — the
deterministic fetch whose stdout stays clean, the isolated reader that returns
structural facts only, and the point where a sub-agent's own permission
classifier denies the script it was spawned to run — is in the skill's
`references/chat-sources.md`.
