# Chat as a source

Chat is the highest-value live source and the most dangerous one. It carries
decisions never written down anywhere else, interleaved with whatever people
happened to paste into a thread. A wiki page or a task board has a shape you
can filter; a conversation's usefulness and its sensitivity are the same
sentences. So this is a different division of labour, not a sweep with extra
care, and every part of it exists because a simpler arrangement failed.

Written against Slack's API shape. The structure transfers to any platform
with conversations, membership, and a privacy flag.

## Scope is membership, read live

Enumerate the conversations the authenticated user is **a member of** — on
Slack, `users.conversations` rather than `conversations.list`, which returns
all public channels regardless of membership. Joining a conversation, or being
added to one, includes it in the next sync: no starring, no hand-kept list, no
channel silently missing because nobody updated a config.

## Let the platform's privacy metadata drive the handling tier

Most workspaces have a convention about where personal data is allowed —
commonly, private channels only. Every channel carries a private flag, readable
live, so the tiering needs no per-channel configuration and a newly created
private channel is handled safely with zero config.

Two independent questions decide how a conversation is handled, and neither
is inferred from the other:

| Axis | Decided by | Yes | No |
|---|---|---|---|
| **Density** — is ordinary traffic per-person records? | the register's `dense_conversations`, named by hand | **summarized**: raw text never enters the export; the isolated agent writes a structural-facts-only summary | pulled verbatim, then gated |
| **Privacy** — is personal data permitted here? | the platform's private flag, or a topic banner listed in `private_topic_markers`, both read live | **scrub-mandatory**: the agent actively removes personal data, summarizing a section only if it is dominated by it | **backstop**: the agent scans for strays |

Density wins where both apply: a dense channel is summarized whether or not it
is private.

- **Density is named by hand** because nothing on the platform says it.
  Scrubbing a message that is nine-tenths personal detail redacts it to
  nothing, so these channels (billing operations, eligibility, support triage)
  lose no durable content to a summary.
- **Privacy is read live**, so a newly created private or bannered channel is
  handled safely with no config change. A banner (matched case-insensitively)
  says what the lock says, and catches a bannered channel left public; it says
  nothing about density.
- **The backstop stays on** for public channels and direct messages, where the
  convention says there is nothing to find. It has caught real personal data
  in a group DM: a convention describes what people intend, not what they did.

## Slack-specific facts

- `oldest` is inclusive: a watermark taken from the newest message reprocesses
  it every sync. Filter with a strict `>`.
- **Thread replies are a separate fetch.** History returns parent messages,
  and on a busy channel the substance is almost entirely in the replies.
- History without a cursor truncates silently; the general trap and its
  detection are in `adding-a-source.md`.

## The script does the mechanical half, and it runs in the main session

Membership lookup, per-conversation incremental fetch, thread replies, noise
filtering, collapsing link unfurls that restate the linked page, grouping, and
computing the new watermark are all deterministic; `sweep-economics.md` covers
why a script owns that half and the stdout contract that makes it safe to run
here.

**Run it from the main session, not from inside the isolated agent.** This is
the counterintuitive part, arrived at by the other arrangement failing
repeatedly:

> An isolated sub-agent spawned to handle sensitive content will have its own
> permission classifier deny the very script call it was spawned to make —
> reasoning that this work belongs in an isolated agent, with no way to see
> that it *is* one. The wrapper's appended system prompt does not reach the
> classifier, and allowlist entries do not help, because that evaluation runs
> independently of the allowlist.

The durable fix is to remove the sub-agent's need to shell out at all: give it
file reading and editing and nothing else, and there is nothing left to deny.

**Check that "and nothing else" is enforced, rather than merely written.** Naming
a tool list is not by itself a confinement, and the flag that looks like one
often is not: an *allow* list usually **adds** to whatever the machine's settings
already permit, so an agent nominally holding two file tools can inherit every
command its owner has ever allowed — and the one gating untrusted content is the
worst place for that surplus, since a prompt injection reaches it as easily as
the model's own judgment does. Find the launcher's *restricting* control — the
one that replaces the tool set and ignores the settings files — and confirm the
denial by asking the agent to do something outside its list and watching it
fail. An agent that quietly did the extra thing is how this gets discovered
otherwise.

## The isolated agent does the judgment half

It reads and edits files, runs no commands, and returns only a confirmation —
never raw content echoed back. Its job is a **faithful gate, not a summary**,
with the designated-channel summaries as the deliberate exception:

- Replace each designated channel's placeholder with a structural-facts-only
  summary, read from the raw side file that placeholder names.
- Scan everything else for stray personal data, omit what it finds, and note
  the omission at the top of the file so it is visible.

**Raw text for the designated channels goes to side files outside the repo**,
which the isolated agent reads and the main session deletes once the summaries
are written. That is sensitive data at rest, briefly, on local disk — a real
trade-off, so write the decision and its date into the register.

Then the export is normal intake: distil it, move it to `inbox/processed/`,
advance the watermark. A conversation that fails to fetch is passed through to
the sync notes, not chased (`sweep-economics.md`).

## What authentication costs, and who decides

Reading history as a person rather than as an installed app generally means a
**user token**, which carries that person's entire read access to the
workspace. Nothing about the export narrows it; the narrowing comes from the
tool's read-only mode and the tiering above. The bundled `slack-client` rides
Slack's undocumented internal API, so a breaking change arrives silently; and
its launcher names `uv run --script` rather than trusting the shebang, since
`#!/usr/bin/env -S` is not portable to Git Bash on Windows.

Two consequences worth stating in the register:

- **Read-only enforced by the tool is worth more than read-only intended by the
  operator.** A mode that rejects write calls outright survives someone
  rewriting the config later.
- **Distributing such a tool to colleagues is a different decision from one
  person using it.** Each additional user authenticates with their own full
  read scope, and an installed app would have been visible to workspace
  administrators in a way a personal token is not. Whether the pipeline's
  handling of personal data is sound is an engineering question; whether the
  organization accepts that token model is not, and it wants an explicit
  sign-off rather than an inference.
